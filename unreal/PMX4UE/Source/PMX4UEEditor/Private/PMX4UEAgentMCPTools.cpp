// Copyright Epic Games, Inc. All Rights Reserved.

#include "PMX4UEAgentMCPTools.h"

#include "Editor.h"
#include "SceneView.h"
#include "AssetCompilingManager.h"
#include "Camera/CameraActor.h"
#include "EditorAssetLibrary.h"
#include "LevelEditorViewport.h"
#include "Animation/SkeletalMeshActor.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/DirectionalLight.h"
#include "Engine/PostProcessVolume.h"
#include "EngineUtils.h"
#include "FileHelpers.h"
#include "HighResScreenshot.h"
#include "ImageUtils.h"
#include "Misc/FileHelper.h"
#include "HAL/IConsoleManager.h"
#include "JsonObjectConverter.h"
#include "MaterialEditingLibrary.h"
#include "MaterialShared.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceConstant.h"
#include "RHIShaderPlatform.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/DirectionalLightComponent.h"

namespace
{
	FString JsonString(const TSharedRef<FJsonObject>& Object)
	{
		FString Output;
		const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
		FJsonSerializer::Serialize(Object, Writer);
		return Output;
	}

	TSharedRef<FJsonObject> ErrorObject(const FString& Message)
	{
		const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
		Result->SetBoolField(TEXT("ok"), false);
		Result->SetStringField(TEXT("error"), Message);
		return Result;
	}

	TSharedRef<FJsonObject> InspectMaterial(UMaterialInterface* Material)
	{
		const TSharedRef<FJsonObject> Json = MakeShared<FJsonObject>();
		if (!Material)
		{
			Json->SetStringField(TEXT("path"), TEXT("None"));
			return Json;
		}

		Json->SetStringField(TEXT("path"), Material->GetPathName());
		Json->SetStringField(TEXT("class"), Material->GetClass()->GetName());
		Json->SetStringField(TEXT("base_material"), Material->GetMaterial() ? Material->GetMaterial()->GetPathName() : TEXT("None"));

		TArray<TSharedPtr<FJsonValue>> Scalars;
		TArray<FMaterialParameterInfo> ScalarInfos;
		TArray<FGuid> ScalarIds;
		Material->GetAllScalarParameterInfo(ScalarInfos, ScalarIds);
		for (const FMaterialParameterInfo& Info : ScalarInfos)
		{
			float Value = 0.0f;
			if (Material->GetScalarParameterValue(Info, Value))
			{
				const TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
				Item->SetStringField(TEXT("name"), Info.Name.ToString());
				Item->SetNumberField(TEXT("value"), Value);
				Scalars.Add(MakeShared<FJsonValueObject>(Item));
			}
		}
		Json->SetArrayField(TEXT("scalars"), Scalars);

		TArray<TSharedPtr<FJsonValue>> Vectors;
		TArray<FMaterialParameterInfo> VectorInfos;
		TArray<FGuid> VectorIds;
		Material->GetAllVectorParameterInfo(VectorInfos, VectorIds);
		for (const FMaterialParameterInfo& Info : VectorInfos)
		{
			FLinearColor Value = FLinearColor::Black;
			if (Material->GetVectorParameterValue(Info, Value))
			{
				const TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
				Item->SetStringField(TEXT("name"), Info.Name.ToString());
				Item->SetNumberField(TEXT("r"), Value.R);
				Item->SetNumberField(TEXT("g"), Value.G);
				Item->SetNumberField(TEXT("b"), Value.B);
				Item->SetNumberField(TEXT("a"), Value.A);
				Vectors.Add(MakeShared<FJsonValueObject>(Item));
			}
		}
		Json->SetArrayField(TEXT("vectors"), Vectors);

		TArray<TSharedPtr<FJsonValue>> Textures;
		TArray<FMaterialParameterInfo> TextureInfos;
		TArray<FGuid> TextureIds;
		Material->GetAllTextureParameterInfo(TextureInfos, TextureIds);
		for (const FMaterialParameterInfo& Info : TextureInfos)
		{
			UTexture* Value = nullptr;
			if (Material->GetTextureParameterValue(Info, Value))
			{
				const TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
				Item->SetStringField(TEXT("name"), Info.Name.ToString());
				Item->SetStringField(TEXT("value"), Value ? Value->GetPathName() : TEXT("None"));
				Textures.Add(MakeShared<FJsonValueObject>(Item));
			}
		}
		Json->SetArrayField(TEXT("textures"), Textures);
		return Json;
	}
}

FString UPMX4UEAgentMCPTools::InspectSkeletalMeshMaterials(const FString& SkeletalMeshAssetPath)
{
	USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, *SkeletalMeshAssetPath);
	if (!Mesh)
	{
		return JsonString(ErrorObject(FString::Printf(TEXT("Skeletal mesh not found: %s"), *SkeletalMeshAssetPath)));
	}

	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), true);
	Result->SetStringField(TEXT("mesh"), Mesh->GetPathName());
	Result->SetNumberField(TEXT("lod_count"), Mesh->GetLODNum());
	Result->SetNumberField(TEXT("material_slot_count"), Mesh->GetMaterials().Num());

	TArray<TSharedPtr<FJsonValue>> Slots;
	for (int32 Index = 0; Index < Mesh->GetMaterials().Num(); ++Index)
	{
		const FSkeletalMaterial& Slot = Mesh->GetMaterials()[Index];
		const TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
		Item->SetNumberField(TEXT("index"), Index);
		Item->SetStringField(TEXT("slot_name"), Slot.MaterialSlotName.ToString());
		Item->SetObjectField(TEXT("material"), InspectMaterial(Slot.MaterialInterface));
		Slots.Add(MakeShared<FJsonValueObject>(Item));
	}
	Result->SetArrayField(TEXT("slots"), Slots);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::InspectCurrentLevelCharacters()
{
	if (!GEditor)
	{
		return JsonString(ErrorObject(TEXT("GEditor is unavailable")));
	}
	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!World)
	{
		return JsonString(ErrorObject(TEXT("No editor world is loaded")));
	}

	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), true);
	Result->SetStringField(TEXT("world"), World->GetPathName());
	TArray<TSharedPtr<FJsonValue>> Components;
	for (TActorIterator<AActor> ActorIt(World); ActorIt; ++ActorIt)
	{
		TInlineComponentArray<USkeletalMeshComponent*> MeshComponents(*ActorIt);
		for (USkeletalMeshComponent* Component : MeshComponents)
		{
			if (!Component || !Component->GetSkeletalMeshAsset())
			{
				continue;
			}
			const TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
			Item->SetStringField(TEXT("actor"), ActorIt->GetActorLabel());
			Item->SetStringField(TEXT("component"), Component->GetPathName());
			Item->SetStringField(TEXT("mesh"), Component->GetSkeletalMeshAsset()->GetPathName());
			Item->SetNumberField(TEXT("material_count"), Component->GetNumMaterials());
			Item->SetBoolField(TEXT("visible"), Component->IsVisible());
			Item->SetBoolField(TEXT("active"), Component->IsActive());
			Item->SetBoolField(TEXT("registered"), Component->IsRegistered());
			Item->SetBoolField(TEXT("render_in_main_pass"), Component->bRenderInMainPass != 0);
			Item->SetBoolField(TEXT("render_custom_depth"), Component->bRenderCustomDepth != 0);
			Item->SetNumberField(TEXT("custom_depth_stencil"), Component->CustomDepthStencilValue);
			Item->SetStringField(TEXT("bounds_origin"), Component->Bounds.Origin.ToString());
			Item->SetStringField(TEXT("bounds_extent"), Component->Bounds.BoxExtent.ToString());
			TArray<TSharedPtr<FJsonValue>> Materials;
			for (int32 MaterialIndex = 0; MaterialIndex < Component->GetNumMaterials(); ++MaterialIndex)
			{
				UMaterialInterface* Material = Component->GetMaterial(MaterialIndex);
				Materials.Add(MakeShared<FJsonValueString>(Material ? Material->GetPathName() : TEXT("None")));
			}
			Item->SetArrayField(TEXT("materials"), Materials);
			Components.Add(MakeShared<FJsonValueObject>(Item));
		}
	}
	Result->SetArrayField(TEXT("skeletal_mesh_components"), Components);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::InspectCurrentLevelDirectionalLights()
{
	if (!GEditor)
	{
		return JsonString(ErrorObject(TEXT("GEditor is unavailable")));
	}
	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!World)
	{
		return JsonString(ErrorObject(TEXT("No editor world is loaded")));
	}

	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), true);
	Result->SetStringField(TEXT("world"), World->GetPathName());
	TArray<TSharedPtr<FJsonValue>> Lights;
	for (TActorIterator<ADirectionalLight> It(World); It; ++It)
	{
		const UDirectionalLightComponent* Component = It->GetComponent();
		const TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
		Item->SetStringField(TEXT("actor"), It->GetActorLabel());
		Item->SetStringField(TEXT("path"), It->GetPathName());
		Item->SetStringField(TEXT("rotation"), It->GetActorRotation().ToString());
		Item->SetStringField(TEXT("surface_to_light_ws"), (-It->GetActorForwardVector()).ToString());
		Item->SetBoolField(TEXT("visible"), !It->IsHiddenEd());
		if (Component)
		{
			Item->SetNumberField(TEXT("intensity"), Component->Intensity);
			Item->SetBoolField(TEXT("atmosphere_sun_light"), Component->bAtmosphereSunLight != 0);
			Item->SetNumberField(TEXT("atmosphere_sun_light_index"), Component->AtmosphereSunLightIndex);
		}
		Lights.Add(MakeShared<FJsonValueObject>(Item));
	}
	Result->SetArrayField(TEXT("directional_lights"), Lights);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::SetDirectionalLightRotation(const FString& ActorLabel, double Pitch, double Yaw, double Roll)
{
	if (!GEditor)
	{
		return JsonString(ErrorObject(TEXT("GEditor is unavailable")));
	}
	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!World)
	{
		return JsonString(ErrorObject(TEXT("No editor world is loaded")));
	}
	ADirectionalLight* Target = nullptr;
	for (TActorIterator<ADirectionalLight> It(World); It; ++It)
	{
		if (It->GetActorLabel().Equals(ActorLabel, ESearchCase::CaseSensitive))
		{
			Target = *It;
			break;
		}
	}
	if (!Target)
	{
		return JsonString(ErrorObject(FString::Printf(TEXT("DirectionalLight not found: %s"), *ActorLabel)));
	}
	Target->Modify();
	Target->SetActorRotation(FRotator(Pitch, Yaw, Roll));
	Target->MarkPackageDirty();
	if (GEditor)
	{
		GEditor->RedrawLevelEditingViewports(true);
	}
	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), true);
	Result->SetStringField(TEXT("actor"), Target->GetActorLabel());
	Result->SetStringField(TEXT("rotation"), Target->GetActorRotation().ToString());
	Result->SetStringField(TEXT("surface_to_light_ws"), (-Target->GetActorForwardVector()).ToString());
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::SetViewportViewMode(const FString& ViewMode)
{
	if (!GEditor)
	{
		return JsonString(ErrorObject(TEXT("GEditor is unavailable")));
	}
	FLevelEditorViewportClient* TargetViewport = nullptr;
	for (FLevelEditorViewportClient* ViewportClient : GEditor->GetLevelViewportClients())
	{
		if (ViewportClient && ViewportClient->IsPerspective() && ViewportClient->IsVisible() && ViewportClient->Viewport)
		{
			TargetViewport = ViewportClient;
			break;
		}
	}
	if (!TargetViewport)
	{
		return JsonString(ErrorObject(TEXT("No perspective level viewport is available")));
	}
	const bool bUnlit = ViewMode.Equals(TEXT("Unlit"), ESearchCase::IgnoreCase);
	const bool bWorldNormal = ViewMode.Equals(TEXT("WorldNormal"), ESearchCase::IgnoreCase);
	if (bWorldNormal) TargetViewport->ChangeBufferVisualizationMode(FName(TEXT("WorldNormal")));
	else TargetViewport->SetViewMode(bUnlit ? VMI_Unlit : VMI_Lit);
	TargetViewport->SetGameView(true);
	TargetViewport->SetRealtime(true);
	TargetViewport->Invalidate();
	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), true);
	Result->SetStringField(TEXT("view_mode"), bWorldNormal ? TEXT("WorldNormal") : bUnlit ? TEXT("Unlit") : TEXT("Lit"));
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::ListAssetsInPath(const FString& ContentPath, const FString& NameContains)
{
	const FString Root = ContentPath.IsEmpty() ? TEXT("/Game/Characters") : ContentPath;
	const TArray<FString> Assets = UEditorAssetLibrary::ListAssets(Root, true, false);
	TArray<TSharedPtr<FJsonValue>> Matches;
	for (const FString& AssetPath : Assets)
	{
		if (NameContains.IsEmpty() || AssetPath.Contains(NameContains, ESearchCase::IgnoreCase))
		{
			Matches.Add(MakeShared<FJsonValueString>(AssetPath));
		}
	}
	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), true);
	Result->SetStringField(TEXT("root"), Root);
	Result->SetStringField(TEXT("filter"), NameContains);
	Result->SetNumberField(TEXT("count"), Matches.Num());
	Result->SetArrayField(TEXT("assets"), Matches);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::DeleteFixedAsset(const FString& AssetPath)
{
	const bool bSafeTarget = AssetPath.StartsWith(TEXT("/Game/Characters/"))
		&& AssetPath.Contains(TEXT("_Fixed"), ESearchCase::CaseSensitive);
	bool bDeleted = false;
	FString Message;
	if (!bSafeTarget)
	{
		Message = TEXT("rejected: path is outside /Game/Characters or does not contain _Fixed");
	}
	else
	{
		bDeleted = UEditorAssetLibrary::DeleteAsset(AssetPath);
		Message = bDeleted ? TEXT("deleted") : TEXT("delete failed");
	}
	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), bDeleted);
	Result->SetStringField(TEXT("path"), AssetPath);
	Result->SetBoolField(TEXT("deleted"), bDeleted);
	Result->SetStringField(TEXT("message"), Message);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::InspectMaterialCompile(const FString& MaterialAssetPath)
{
	UMaterial* Material = LoadObject<UMaterial>(nullptr, *MaterialAssetPath);
	if (!Material)
	{
		return JsonString(ErrorObject(FString::Printf(TEXT("Material not found: %s"), *MaterialAssetPath)));
	}
	UMaterialEditingLibrary::RecompileMaterial(Material);
	FAssetCompilingManager::Get().FinishAllCompilation();
	FMaterialResource* Resource = Material->GetMaterialResource(GMaxRHIShaderPlatform);
	TArray<TSharedPtr<FJsonValue>> Errors;
	if (Resource)
	{
		for (const FString& Error : Resource->GetCompileErrors())
		{
			Errors.Add(MakeShared<FJsonValueString>(Error));
		}
	}
	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), Resource != nullptr && Errors.IsEmpty());
	Result->SetStringField(TEXT("material"), Material->GetPathName());
	Result->SetStringField(TEXT("shader_platform"), LegacyShaderPlatformToShaderFormat(GMaxRHIShaderPlatform).ToString());
	Result->SetNumberField(TEXT("error_count"), Errors.Num());
	Result->SetArrayField(TEXT("errors"), Errors);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::AlignViewportToCamera(const FString& CameraActorLabel, double AzimuthDegrees, double Distance, double HeightOffset, double FieldOfView, const FString& ActorLabel)
{
	if (!GEditor)
	{
		return JsonString(ErrorObject(TEXT("GEditor is unavailable")));
	}
	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!World)
	{
		return JsonString(ErrorObject(TEXT("No editor world is loaded")));
	}
	ACameraActor* TargetCamera = nullptr;
	if (!CameraActorLabel.IsEmpty())
	{
		for (TActorIterator<ACameraActor> It(World); It; ++It)
		{
			if (It->GetActorLabel().Equals(CameraActorLabel, ESearchCase::CaseSensitive))
			{
				TargetCamera = *It;
				break;
			}
		}
	}
	FVector LookAtPoint(0.0, 0.0, 95.0);
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (!ActorLabel.IsEmpty() && !It->GetActorLabel().Equals(ActorLabel, ESearchCase::CaseSensitive))
		{
			continue;
		}
		if (USkeletalMeshComponent* MeshComponent = It->FindComponentByClass<USkeletalMeshComponent>())
		{
			LookAtPoint = MeshComponent->Bounds.Origin;
			break;
		}
	}
	const double SafeDistance = FMath::Clamp(Distance, 100.0, 1200.0);
	const double AzimuthRadians = FMath::DegreesToRadians(AzimuthDegrees);
	const FVector CameraLocation = LookAtPoint + FVector(
		FMath::Cos(AzimuthRadians) * SafeDistance,
		FMath::Sin(AzimuthRadians) * SafeDistance,
		FMath::Clamp(HeightOffset, -100.0, 200.0));
	const FRotator LookAtRotation = (LookAtPoint - CameraLocation).Rotation();
	if (TargetCamera)
	{
		TargetCamera->SetActorLocation(CameraLocation);
		TargetCamera->SetActorRotation(LookAtRotation);
	}

	FLevelEditorViewportClient* TargetViewport = nullptr;
	for (FLevelEditorViewportClient* ViewportClient : GEditor->GetLevelViewportClients())
	{
		if (ViewportClient && ViewportClient->IsPerspective())
		{
			TargetViewport = ViewportClient;
			break;
		}
	}
	if (!TargetViewport && GEditor->GetLevelViewportClients().Num() > 0)
	{
		TargetViewport = GEditor->GetLevelViewportClients()[0];
	}
	if (!TargetViewport)
	{
		return JsonString(ErrorObject(TEXT("No level editor viewport is available")));
	}
	TargetViewport->SetViewportType(LVT_Perspective);
	TargetViewport->SetViewMode(VMI_Lit);
	TargetViewport->SetViewLocation(CameraLocation);
	TargetViewport->SetViewRotation(LookAtRotation);
	TargetViewport->ViewFOV = FMath::Clamp(static_cast<float>(FieldOfView), 20.0f, 90.0f);
	TargetViewport->FOVAngle = TargetViewport->ViewFOV;
	TargetViewport->SetGameView(true);
	TargetViewport->SetRealtime(true);
	TargetViewport->Invalidate();

	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), true);
	Result->SetStringField(TEXT("camera"), TargetCamera ? TargetCamera->GetPathName() : TEXT("None (viewport-only alignment)"));
	Result->SetStringField(TEXT("location"), CameraLocation.ToString());
	Result->SetStringField(TEXT("look_at"), LookAtPoint.ToString());
	Result->SetStringField(TEXT("rotation"), LookAtRotation.ToString());
	Result->SetNumberField(TEXT("azimuth_degrees"), AzimuthDegrees);
	Result->SetNumberField(TEXT("distance"), SafeDistance);
	Result->SetNumberField(TEXT("field_of_view"), TargetViewport->ViewFOV);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::SetMaterialScalarParameter(const FString& MaterialInstancePath, const FString& ParameterName, double Value, bool bSaveAsset)
{
	UMaterialInstanceConstant* Instance = LoadObject<UMaterialInstanceConstant>(nullptr, *MaterialInstancePath);
	if (!Instance)
	{
		return JsonString(ErrorObject(FString::Printf(TEXT("Material instance not found: %s"), *MaterialInstancePath)));
	}
	Instance->Modify();
	Instance->SetScalarParameterValueEditorOnly(FMaterialParameterInfo(*ParameterName), static_cast<float>(Value));
	Instance->PostEditChange();
	Instance->MarkPackageDirty();
	const bool bSaved = !bSaveAsset || UEditorAssetLibrary::SaveLoadedAsset(Instance, false);
	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), bSaved);
	Result->SetStringField(TEXT("material"), Instance->GetPathName());
	Result->SetStringField(TEXT("parameter"), ParameterName);
	Result->SetNumberField(TEXT("value"), Value);
	Result->SetBoolField(TEXT("saved"), bSaveAsset && bSaved);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::SetMaterialVectorParameter(const FString& MaterialInstancePath, const FString& ParameterName, double Red, double Green, double Blue, double Alpha, bool bSaveAsset)
{
	UMaterialInstanceConstant* Instance = LoadObject<UMaterialInstanceConstant>(nullptr, *MaterialInstancePath);
	if (!Instance)
	{
		return JsonString(ErrorObject(FString::Printf(TEXT("Material instance not found: %s"), *MaterialInstancePath)));
	}
	const FLinearColor Value(static_cast<float>(Red), static_cast<float>(Green), static_cast<float>(Blue), static_cast<float>(Alpha));
	Instance->Modify();
	Instance->SetVectorParameterValueEditorOnly(FMaterialParameterInfo(*ParameterName), Value);
	Instance->PostEditChange();
	Instance->MarkPackageDirty();
	const bool bSaved = !bSaveAsset || UEditorAssetLibrary::SaveLoadedAsset(Instance, false);
	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), bSaved);
	Result->SetStringField(TEXT("material"), Instance->GetPathName());
	Result->SetStringField(TEXT("parameter"), ParameterName);
	Result->SetStringField(TEXT("value"), Value.ToString());
	Result->SetBoolField(TEXT("saved"), bSaveAsset && bSaved);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::SetCharacterOutlineOverlay(const FString& ActorLabel, const FString& OverlayMaterialPath, const FString& FaceOverlayMaterialPath, const FString& HairOverlayMaterialPath, const FString& ExcludedSlotIndices, const FString& FaceSlotIndices, const FString& HairSlotIndices, double MaxDrawDistance, bool bSaveLevel)
{
	if (!GEditor)
	{
		return JsonString(ErrorObject(TEXT("GEditor is unavailable")));
	}
	if (ActorLabel.IsEmpty() || OverlayMaterialPath.IsEmpty())
	{
		return JsonString(ErrorObject(TEXT("ActorLabel and OverlayMaterialPath are required")));
	}
	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!World)
	{
		return JsonString(ErrorObject(TEXT("No editor world is loaded")));
	}
	UMaterialInterface* OverlayMaterial = LoadObject<UMaterialInterface>(nullptr, *OverlayMaterialPath);
	if (!OverlayMaterial)
	{
		return JsonString(ErrorObject(FString::Printf(TEXT("Overlay material not found: %s"), *OverlayMaterialPath)));
	}
	UMaterialInterface* FaceOverlayMaterial = FaceOverlayMaterialPath.IsEmpty() ? nullptr : LoadObject<UMaterialInterface>(nullptr, *FaceOverlayMaterialPath);
	UMaterialInterface* HairOverlayMaterial = HairOverlayMaterialPath.IsEmpty() ? nullptr : LoadObject<UMaterialInterface>(nullptr, *HairOverlayMaterialPath);
	if ((!FaceOverlayMaterialPath.IsEmpty() && !FaceOverlayMaterial) || (!HairOverlayMaterialPath.IsEmpty() && !HairOverlayMaterial))
	{
		return JsonString(ErrorObject(TEXT("A requested face or hair outline material was not found")));
	}

	AActor* TargetActor = nullptr;
	USkeletalMeshComponent* TargetComponent = nullptr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->GetActorLabel().Equals(ActorLabel, ESearchCase::IgnoreCase))
		{
			TInlineComponentArray<USkeletalMeshComponent*> Components(*It);
			for (USkeletalMeshComponent* Component : Components)
			{
				if (Component && Component->GetSkeletalMeshAsset())
				{
					TargetActor = *It;
					TargetComponent = Component;
					break;
				}
			}
		}
		if (TargetComponent)
		{
			break;
		}
	}
	if (!TargetComponent || !TargetActor)
	{
		return JsonString(ErrorObject(FString::Printf(TEXT("Skeletal mesh actor not found: %s"), *ActorLabel)));
	}

	auto ParseIndexSet = [](const FString& Value)
	{
		TSet<int32> Result;
		TArray<FString> Tokens;
		Value.ParseIntoArray(Tokens, TEXT(","), true);
		for (FString Token : Tokens)
		{
			Token.TrimStartAndEndInline();
			if (!Token.IsEmpty() && Token.IsNumeric())
			{
				Result.Add(FCString::Atoi(*Token));
			}
		}
		return Result;
	};
	const TSet<int32> ExcludedSlots = ParseIndexSet(ExcludedSlotIndices);
	const TSet<int32> FaceSlots = ParseIndexSet(FaceSlotIndices);
	const TSet<int32> HairSlots = ParseIndexSet(HairSlotIndices);

	TargetActor->Modify();
	TargetComponent->Modify();
	TargetComponent->SetOverlayMaterial(nullptr);
	TArray<TSharedPtr<FJsonValue>> AppliedSlots;
	TArray<TSharedPtr<FJsonValue>> ExcludedSlotJson;
	for (int32 SlotIndex = 0; SlotIndex < TargetComponent->GetNumMaterials(); ++SlotIndex)
	{
		const bool bExcluded = ExcludedSlots.Contains(SlotIndex);
		UMaterialInterface* SlotOverlay = OverlayMaterial;
		if (FaceOverlayMaterial && FaceSlots.Contains(SlotIndex))
		{
			SlotOverlay = FaceOverlayMaterial;
		}
		else if (HairOverlayMaterial && HairSlots.Contains(SlotIndex))
		{
			SlotOverlay = HairOverlayMaterial;
		}
		TargetComponent->SetOverlayMaterial(bExcluded ? nullptr : SlotOverlay, true, SlotIndex);
		(bExcluded ? ExcludedSlotJson : AppliedSlots).Add(MakeShared<FJsonValueNumber>(SlotIndex));
	}
	TargetComponent->SetOverlayMaterialMaxDrawDistance(FMath::Max(0.0f, static_cast<float>(MaxDrawDistance)));
	TargetComponent->MarkRenderStateDirty();
	TargetActor->MarkPackageDirty();
	const bool bSaved = !bSaveLevel || UEditorLoadingAndSavingUtils::SaveDirtyPackages(true, true);

	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), bSaved);
	Result->SetStringField(TEXT("world"), World->GetPathName());
	Result->SetStringField(TEXT("actor"), TargetActor->GetActorLabel());
	Result->SetStringField(TEXT("component"), TargetComponent->GetPathName());
	Result->SetStringField(TEXT("overlay_material"), OverlayMaterial->GetPathName());
	Result->SetStringField(TEXT("face_overlay_material"), FaceOverlayMaterial ? FaceOverlayMaterial->GetPathName() : TEXT("None"));
	Result->SetStringField(TEXT("hair_overlay_material"), HairOverlayMaterial ? HairOverlayMaterial->GetPathName() : TEXT("None"));
	Result->SetArrayField(TEXT("applied_slots"), AppliedSlots);
	Result->SetArrayField(TEXT("excluded_slots"), ExcludedSlotJson);
	Result->SetNumberField(TEXT("max_draw_distance"), MaxDrawDistance);
	Result->SetBoolField(TEXT("saved"), bSaveLevel && bSaved);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::SetCharacterDepthRim(const FString& ActorLabel, const FString& RimMaterialPath, int32 StencilValue, double BlendWeight, bool bSaveLevel)
{
	if (!GEditor)
	{
		return JsonString(ErrorObject(TEXT("GEditor is unavailable")));
	}
	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!World)
	{
		return JsonString(ErrorObject(TEXT("No editor world is loaded")));
	}
	if (ActorLabel.IsEmpty() || RimMaterialPath.IsEmpty())
	{
		return JsonString(ErrorObject(TEXT("ActorLabel and RimMaterialPath are required")));
	}
	UMaterialInterface* RimMaterial = LoadObject<UMaterialInterface>(nullptr, *RimMaterialPath);
	if (!RimMaterial)
	{
		return JsonString(ErrorObject(FString::Printf(TEXT("Rim material not found: %s"), *RimMaterialPath)));
	}

	AActor* TargetActor = nullptr;
	USkeletalMeshComponent* TargetComponent = nullptr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->GetActorLabel().Equals(ActorLabel, ESearchCase::IgnoreCase))
		{
			TInlineComponentArray<USkeletalMeshComponent*> Components(*It);
			for (USkeletalMeshComponent* Component : Components)
			{
				if (Component && Component->GetSkeletalMeshAsset())
				{
					TargetActor = *It;
					TargetComponent = Component;
					break;
				}
			}
		}
		if (TargetComponent)
		{
			break;
		}
	}
	if (!TargetComponent || !TargetActor)
	{
		return JsonString(ErrorObject(FString::Printf(TEXT("Skeletal mesh actor not found: %s"), *ActorLabel)));
	}

	TargetActor->Modify();
	TargetComponent->Modify();
	const bool bEnableRim = BlendWeight > KINDA_SMALL_NUMBER;
	TargetComponent->SetRenderCustomDepth(bEnableRim);
	TargetComponent->SetCustomDepthStencilValue(FMath::Clamp(StencilValue, 1, 255));
	TargetComponent->MarkRenderStateDirty();
	TargetActor->MarkPackageDirty();

	APostProcessVolume* RimVolume = nullptr;
	for (TActorIterator<APostProcessVolume> It(World); It; ++It)
	{
		if (It->GetActorLabel().EndsWith(TEXT("_DepthRim"), ESearchCase::IgnoreCase))
		{
			RimVolume = *It;
			break;
		}
	}
	if (!RimVolume)
	{
		RimVolume = World->SpawnActor<APostProcessVolume>(FVector::ZeroVector, FRotator::ZeroRotator);
		if (!RimVolume)
		{
			return JsonString(ErrorObject(TEXT("Failed to spawn depth-rim post-process volume")));
		}
		RimVolume->SetActorLabel(TEXT("PMX4UE_DepthRim"));
	}

	RimVolume->Modify();
	RimVolume->bUnbound = true;
	RimVolume->BlendWeight = bEnableRim ? 1.0f : 0.0f;
	for (int32 Index = RimVolume->Settings.WeightedBlendables.Array.Num() - 1; Index >= 0; --Index)
	{
		if (RimVolume->Settings.WeightedBlendables.Array[Index].Object == RimMaterial)
		{
			RimVolume->Settings.WeightedBlendables.Array.RemoveAt(Index);
		}
	}
	if (bEnableRim)
	{
		RimVolume->Settings.WeightedBlendables.Array.Add(
			FWeightedBlendable(FMath::Clamp(static_cast<float>(BlendWeight), 0.0f, 1.0f), RimMaterial)
		);
	}
	RimVolume->MarkPackageDirty();
	const bool bSaved = !bSaveLevel || UEditorLoadingAndSavingUtils::SaveDirtyPackages(true, true);

	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), bSaved);
	Result->SetStringField(TEXT("world"), World->GetPathName());
	Result->SetStringField(TEXT("actor"), TargetActor->GetActorLabel());
	Result->SetStringField(TEXT("component"), TargetComponent->GetPathName());
	Result->SetStringField(TEXT("rim_material"), RimMaterial->GetPathName());
	Result->SetStringField(TEXT("post_process_volume"), RimVolume->GetPathName());
	Result->SetNumberField(TEXT("stencil_value"), FMath::Clamp(StencilValue, 1, 255));
	Result->SetNumberField(TEXT("blend_weight"), FMath::Clamp(BlendWeight, 0.0, 1.0));
	Result->SetBoolField(TEXT("enabled"), bEnableRim);
	Result->SetBoolField(TEXT("saved"), bSaveLevel && bSaved);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::CaptureEditorViewport(const FString& OutputFilename, int32 Width, int32 Height)
{
	if (!GEditor)
	{
		return JsonString(ErrorObject(TEXT("GEditor is unavailable")));
	}
	FLevelEditorViewportClient* TargetViewport = nullptr;
	for (FLevelEditorViewportClient* ViewportClient : GEditor->GetLevelViewportClients())
	{
		if (ViewportClient && ViewportClient->IsPerspective())
		{
			TargetViewport = ViewportClient;
			break;
		}
	}
	if (!TargetViewport && GEditor->GetLevelViewportClients().Num() > 0)
	{
		TargetViewport = GEditor->GetLevelViewportClients()[0];
	}
	if (!TargetViewport)
	{
		return JsonString(ErrorObject(TEXT("No level editor viewport is available")));
	}
	const FString SafeFilename = FPaths::GetCleanFilename(OutputFilename.IsEmpty() ? TEXT("PMX4UE_MCP.png") : OutputFilename);
	const FString OutputDirectory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("PMX4UECaptures"));
	IFileManager::Get().MakeDirectory(*OutputDirectory, true);
	const FString OutputPath = FPaths::Combine(OutputDirectory, SafeFilename);

	FHighResScreenshotConfig& Config = GetHighResScreenshotConfig();
	Config.SetResolution(FMath::Clamp(Width, 256, 4096), FMath::Clamp(Height, 256, 4096), 1.0f);
	Config.FilenameOverride = OutputPath;
	TargetViewport->TakeHighResScreenShot();
	// A background or unfocused editor viewport may not redraw promptly, which
	// leaves the high-resolution screenshot request queued indefinitely.  MCP
	// capture is part of the automated material validation path, so explicitly
	// invalidate and draw the selected viewport after scheduling the request.
	TargetViewport->Invalidate();
	if (TargetViewport->Viewport)
	{
		TargetViewport->Viewport->Draw();
	}

	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), true);
	Result->SetStringField(TEXT("status"), TEXT("scheduled"));
	Result->SetStringField(TEXT("output_path"), OutputPath);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::FramePreviewSubject(const FString& ActorLabel, const FString& CameraJson, bool bApply)
{
	if (!GEditor || ActorLabel.IsEmpty())
		return JsonString(ErrorObject(TEXT("Preview actor label and editor are required")));
	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!World) return JsonString(ErrorObject(TEXT("No editor world")));
	USkeletalMeshComponent* Mesh = nullptr;
	AActor* Subject = nullptr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->GetActorLabel() == ActorLabel)
		{
			if (Subject) return JsonString(ErrorObject(TEXT("Ambiguous preview actor label")));
			Subject = *It;
			Mesh = It->FindComponentByClass<USkeletalMeshComponent>();
		}
	}
	if (!Subject || !Mesh || !Mesh->GetSkeletalMeshAsset() || !Mesh->IsRegistered())
		return JsonString(ErrorObject(TEXT("Preview subject mesh is unavailable")));
	if (Subject->IsHidden() || Subject->IsHiddenEd() || !Mesh->IsVisible() || Mesh->bHiddenInGame)
		return JsonString(ErrorObject(TEXT("Preview subject is hidden; refusing empty-scene capture")));
	FLevelEditorViewportClient* Target = nullptr;
	for (FLevelEditorViewportClient* Client : GEditor->GetLevelViewportClients())
		if (Client && Client->IsPerspective() && Client->IsVisible() && Client->Viewport)
		{ Target = Client; break; }
	if (!Target) return JsonString(ErrorObject(TEXT("No visible perspective viewport")));
	const FIntPoint Size = Target->Viewport->GetSizeXY();
	if (Size.X <= 0 || Size.Y <= 0) return JsonString(ErrorObject(TEXT("Viewport has no drawable pixels")));
	TSharedPtr<FJsonObject> Spec;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(CameraJson), Spec) || !Spec.IsValid())
		return JsonString(ErrorObject(TEXT("Invalid camera JSON")));
	FString Kind;
	double Azimuth = 0, Elevation = 0, Fov = 0, Margin = 0;
	if (!Spec->TryGetStringField(TEXT("kind"), Kind) ||
		!Spec->TryGetNumberField(TEXT("azimuth"), Azimuth) ||
		!Spec->TryGetNumberField(TEXT("elevation"), Elevation) ||
		!Spec->TryGetNumberField(TEXT("fov"), Fov) ||
		!Spec->TryGetNumberField(TEXT("margin"), Margin) ||
		!FMath::IsFinite(Azimuth) || !FMath::IsFinite(Elevation) || !FMath::IsFinite(Fov) ||
		!FMath::IsFinite(Margin) || Fov < 20 || Fov > 90 || Margin < .02 || Margin > .2 ||
		FMath::Abs(Elevation) > 80)
		return JsonString(ErrorObject(TEXT("Invalid framing parameters")));
	auto ReadVector = [&](const TCHAR* Key, FVector& Out) -> bool
	{
		const TArray<TSharedPtr<FJsonValue>>* Values;
		if (!Spec->TryGetArrayField(Key, Values) || Values->Num() != 3) return false;
		for (int32 I = 0; I < 3; ++I)
			if (!(*Values)[I]->TryGetNumber(Out[I]) || !FMath::IsFinite(Out[I])) return false;
		return true;
	};
	const FBox Box = Mesh->Bounds.GetBox();
	FVector Center = Box.GetCenter(), Extent = Box.GetExtent();
	FString TargetName = TEXT("mesh_bounds");
	if (Kind == TEXT("detail"))
	{
		FVector Offset;
		if (!ReadVector(TEXT("extent_cm"), Extent) || Extent.GetMin() <= 0 ||
			!ReadVector(TEXT("offset_cm"), Offset))
			return JsonString(ErrorObject(TEXT("Detail requires positive extent_cm and offset_cm")));
		FString Bone;
		if (Spec->TryGetStringField(TEXT("bone"), Bone) && !Bone.IsEmpty())
		{
			const int32 Index = Mesh->GetBoneIndex(FName(*Bone));
			if (Index == INDEX_NONE) return JsonString(ErrorObject(TEXT("Detail target bone does not exist: ") + Bone));
			Center = Mesh->GetBoneLocation(FName(*Bone), EBoneSpaces::WorldSpace);
			TargetName = Bone;
		}
		else
		{
			FVector Fraction;
			if (!ReadVector(TEXT("bounds_fraction"), Fraction) || Fraction.GetAbsMax() > 1)
				return JsonString(ErrorObject(TEXT("Detail requires actual bone or bounds_fraction in [-1,1]")));
			Center = Box.GetCenter() + Box.GetExtent() * Fraction;
			TargetName = TEXT("bounds_fraction");
		}
		Center += Offset;
		if (!Box.IsInsideOrOn(Center))
			return JsonString(ErrorObject(TEXT("Detail target lies outside subject bounds")));
	}
	else if (Kind != TEXT("full_body"))
		return JsonString(ErrorObject(TEXT("Explicit full_body/detail framing is required")));
	if (Extent.GetMin() <= 0 || Extent.ContainsNaN())
		return JsonString(ErrorObject(TEXT("Subject bounds are invalid")));
	const FVector Direction = FRotator(Elevation, Azimuth, 0).Vector();
	double Distance = FMath::Max(Extent.Size() * 3., 10.);
	FVector2D Min, Max;
	bool InFront = false;
	auto Measure = [&]()
	{
		FSceneViewFamilyContext Family(FSceneViewFamily::ConstructionValues(
			Target->Viewport, World->Scene, Target->EngineShowFlags).SetRealtimeUpdate(true));
		FSceneView* View = Target->CalcSceneView(&Family);
		Min = FVector2D(1.e10, 1.e10); Max = FVector2D(-1.e10, -1.e10);
		InFront = true;
		for (int32 I = 0; I < 8; ++I)
		{
			const FVector Corner = Center + Extent * FVector(I & 1 ? 1 : -1, I & 2 ? 1 : -1, I & 4 ? 1 : -1);
			FVector2D Pixel;
			if (!FSceneView::ProjectWorldToScreen(Corner, View->UnscaledViewRect,
				View->ViewMatrices.GetWorldToClip(), Pixel))
			{ InFront = false; continue; }
			const FVector2D UV(Pixel.X / Size.X, Pixel.Y / Size.Y);
			Min.X = FMath::Min(Min.X, UV.X); Min.Y = FMath::Min(Min.Y, UV.Y);
			Max.X = FMath::Max(Max.X, UV.X); Max.Y = FMath::Max(Max.Y, UV.Y);
		}
	};
	if (bApply)
	{
		Target->SetViewRotation((-Direction).Rotation());
		Target->ViewFOV = Fov; Target->FOVAngle = Fov;
		Target->SetGameView(true); Target->SetRealtime(true);
		// Fit real projected corners, including perspective depth and actual viewport aspect.
		for (int32 Iteration = 0; Iteration < 32; ++Iteration)
		{
			Target->SetViewLocation(Center + Direction * Distance);
			Measure();
			const double Radius = FMath::Max(FMath::Max(.5-Min.X, .5-Min.Y), FMath::Max(Max.X-.5, Max.Y-.5));
			const double Ratio = Radius / (.5 - Margin);
			if (InFront && Ratio >= .98 && Ratio <= 1.) break;
			Distance *= !InFront ? 2. : FMath::Clamp(Ratio * 1.005, .8, 2.);
		}
		Target->Invalidate();
	}
	Measure();
	const double Occupancy = FMath::Max(Max.X - Min.X, Max.Y - Min.Y);
	const bool Fits = InFront && Min.X >= Margin - .005 && Min.Y >= Margin - .005 &&
		Max.X <= 1.-Margin+.005 && Max.Y <= 1.-Margin+.005 && Occupancy >= .5;
	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), Fits);
	if (!Fits) Result->SetStringField(TEXT("error"), TEXT("Subject framing clipped, behind camera or too small; recapture after fitting"));
	Result->SetStringField(TEXT("schema"), TEXT("pmx4ue.subject-frame.v1"));
	Result->SetStringField(TEXT("actor"), Subject->GetPathName());
	Result->SetStringField(TEXT("mesh"), Mesh->GetSkeletalMeshAsset()->GetPathName());
	Result->SetStringField(TEXT("kind"), Kind);
	Result->SetStringField(TEXT("target"), TargetName);
	Result->SetBoolField(TEXT("subject_visible"), true);
	Result->SetBoolField(TEXT("in_front"), InFront);
	Result->SetNumberField(TEXT("viewport_width"), Size.X);
	Result->SetNumberField(TEXT("viewport_height"), Size.Y);
	Result->SetNumberField(TEXT("occupancy"), Occupancy);
	Result->SetNumberField(TEXT("margin"), Margin);
	Result->SetNumberField(TEXT("fov"), Target->ViewFOV);
	Result->SetStringField(TEXT("look_at"), Center.ToString());
	Result->SetStringField(TEXT("location"), Target->GetViewLocation().ToString());
	Result->SetArrayField(TEXT("rect"), {MakeShared<FJsonValueNumber>(Min.X), MakeShared<FJsonValueNumber>(Min.Y),
		MakeShared<FJsonValueNumber>(Max.X), MakeShared<FJsonValueNumber>(Max.Y)});
	Result->SetStringField(TEXT("scope"), TEXT("Visibility and projected bounds only; occlusion and appearance require image review"));
	return JsonString(Result);
}
FString UPMX4UEAgentMCPTools::CaptureVisibleEditorViewport(const FString& OutputFilename, const FString& ActorLabel, const FString& CameraJson)
{
	if (!GEditor)
	{
		return JsonString(ErrorObject(TEXT("GEditor is unavailable")));
	}
	FLevelEditorViewportClient* Target = nullptr;
	for (FLevelEditorViewportClient* Client : GEditor->GetLevelViewportClients())
	{
		if (Client && Client->IsPerspective() && Client->IsVisible() && Client->Viewport)
		{
			Target = Client;
			break;
		}
	}
	if (!Target)
	{
		return JsonString(ErrorObject(TEXT("No visible perspective level viewport; open and enlarge the editor viewport")));
	}
	const FIntPoint Size = Target->Viewport->GetSizeXY();
	if (Size.X <= 0 || Size.Y <= 0)
	{
		return JsonString(ErrorObject(TEXT("Visible viewport has no drawable pixels")));
	}
	const FString SafeName = FPaths::GetCleanFilename(OutputFilename);
	if (SafeName.IsEmpty() || !SafeName.EndsWith(TEXT(".png"), ESearchCase::IgnoreCase))
	{
		return JsonString(ErrorObject(TEXT("Capture filename must be a PNG")));
	}
	const FString Directory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("PMX4UECaptures"));
	IFileManager::Get().MakeDirectory(*Directory, true);
	const FString Path = FPaths::Combine(Directory, SafeName);
	if (IFileManager::Get().FileExists(*Path))
	{
		return JsonString(ErrorObject(TEXT("Capture already exists; choose a new run")));
	}
	Target->Invalidate();
	Target->Viewport->Draw();
	TSharedPtr<FJsonObject> Framing;
	if (!ActorLabel.IsEmpty() || !CameraJson.IsEmpty())
	{
		const FString Receipt = FramePreviewSubject(ActorLabel, CameraJson, false);
		if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Receipt), Framing) ||
			!Framing.IsValid() || !Framing->GetBoolField(TEXT("ok")))
			return Receipt;
	}
	TArray<FColor> Pixels;
	if (!Target->Viewport->ReadPixels(Pixels) || Pixels.Num() != Size.X * Size.Y)
	{
		return JsonString(ErrorObject(TEXT("Visible viewport backbuffer read failed")));
	}
	// Scene screenshots are opaque. Backbuffer alpha is not a coverage mask.
	for (FColor& Pixel : Pixels)
	{
		Pixel.A = 255;
	}
	TArray64<uint8> Png;
	FImageUtils::PNGCompressImageArray(Size.X, Size.Y, TArrayView64<const FColor>(Pixels.GetData(), Pixels.Num()), Png);
	if (Png.IsEmpty() || !FFileHelper::SaveArrayToFile(Png, *Path))
	{
		return JsonString(ErrorObject(TEXT("Could not write visible viewport PNG")));
	}
	const IConsoleVariable* ScreenPercentage = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage"));
	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), true);
	Result->SetStringField(TEXT("source"), TEXT("visible_viewport_backbuffer"));
	if (Framing.IsValid()) Result->SetObjectField(TEXT("framing"), Framing);
	Result->SetStringField(TEXT("alpha_policy"), TEXT("opaque_scene"));
	Result->SetStringField(TEXT("output_path"), Path);
	Result->SetNumberField(TEXT("width"), Size.X);
	Result->SetNumberField(TEXT("height"), Size.Y);
	Result->SetNumberField(TEXT("r_screen_percentage_setting"), ScreenPercentage ? ScreenPercentage->GetFloat() : -1.0f);
	return JsonString(Result);
}

FString UPMX4UEAgentMCPTools::CheckPreviewTextureResidency(const FString& ActorLabel, float HoldSeconds)
{
	if (!GEditor || ActorLabel.IsEmpty())
	{
		return JsonString(ErrorObject(TEXT("Editor and preview actor label are required")));
	}
	UWorld* World = GEditor->GetEditorWorldContext().World();
	if (!World)
	{
		return JsonString(ErrorObject(TEXT("No editor world is loaded")));
	}
	USkeletalMeshComponent* Mesh = nullptr;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (It->GetActorLabel().Equals(ActorLabel, ESearchCase::CaseSensitive))
		{
			Mesh = It->FindComponentByClass<USkeletalMeshComponent>();
			break;
		}
	}
	if (!Mesh)
	{
		return JsonString(ErrorObject(TEXT("Preview skeletal mesh actor not found")));
	}
	TSet<UTexture2D*> UniqueTextures;
	for (int32 Slot = 0; Slot < Mesh->GetNumMaterials(); ++Slot)
	{
		if (UMaterialInterface* Material = Mesh->GetMaterial(Slot))
		{
			TArray<UTexture*> Used;
			Material->GetUsedTextures(Used);
			for (UTexture* Texture : Used)
			{
				if (UTexture2D* Texture2D = Cast<UTexture2D>(Texture))
				{
					if (Texture2D->GetPathName().StartsWith(TEXT("/Game/")))
					{
						UniqueTextures.Add(Texture2D);
					}
				}
			}
		}
	}
	if (UniqueTextures.IsEmpty())
	{
		return JsonString(ErrorObject(TEXT("No /Game Texture2D used by preview materials; cannot validate texture loading")));
	}
	TArray<TSharedPtr<FJsonValue>> Rows;
	int32 Pending = 0;
	for (UTexture2D* Texture : UniqueTextures)
	{
		Texture->SetForceMipLevelsToBeResident(FMath::Clamp(HoldSeconds, 1.0f, 120.0f));
		const FStreamableRenderResourceState& State = Texture->GetStreamableResourceState();
		const int32 Available = State.MaxNumLODs;
		const int32 Resident = Texture->GetNumResidentMips();
		const bool bReady = Available > 0 && Resident >= Available;
		Pending += bReady ? 0 : 1;
		const TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
		Row->SetStringField(TEXT("path"), Texture->GetPathName());
		Row->SetNumberField(TEXT("available_mips"), Available);
		Row->SetNumberField(TEXT("resident_mips"), Resident);
		Row->SetBoolField(TEXT("ready"), bReady);
		Rows.Add(MakeShared<FJsonValueObject>(Row));
	}
	const TSharedRef<FJsonObject> Result = MakeShared<FJsonObject>();
	Result->SetBoolField(TEXT("ok"), true);
	Result->SetBoolField(TEXT("ready"), Pending == 0);
	Result->SetNumberField(TEXT("checked"), UniqueTextures.Num());
	Result->SetNumberField(TEXT("pending"), Pending);
	Result->SetArrayField(TEXT("textures"), Rows);
	return JsonString(Result);
}
