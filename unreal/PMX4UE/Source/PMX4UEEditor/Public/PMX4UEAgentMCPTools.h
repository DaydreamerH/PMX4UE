// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "PMX4UEAgentMCPTools.generated.h"

/** MCP tools used by the reusable MMD-to-Unreal character pipeline. */
UCLASS()
class PMX4UEEDITOR_API UPMX4UEAgentMCPTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** Returns a JSON audit of a skeletal mesh, its material slots, material instances, and all parameter values. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString InspectSkeletalMeshMaterials(const FString& SkeletalMeshAssetPath);

	/** Returns a JSON summary of every skeletal mesh component in the currently loaded editor level. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString InspectCurrentLevelCharacters();

	/** Returns the rotation and atmosphere-sun configuration of directional lights in the current level. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString InspectCurrentLevelDirectionalLights();

	/** Temporarily rotates a named directional light for live material-response validation. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString SetDirectionalLightRotation(const FString& ActorLabel, double Pitch, double Yaw, double Roll = 0.0);

	/** Lists project assets under a content path, optionally filtered by a case-insensitive name fragment. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString ListAssetsInPath(const FString& ContentPath = "/Game/Characters", const FString& NameContains = "");

	/** Deletes one explicitly supplied character asset path containing _Fixed. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString DeleteFixedAsset(const FString& AssetPath);

	/** Recompiles a material inside the running editor and returns its shader compile errors. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString InspectMaterialCompile(const FString& MaterialAssetPath);

	/** Aligns a perspective level viewport to a named CameraActor (or the viewport only when the label is empty). */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString AlignViewportToCamera(const FString& CameraActorLabel = "", double AzimuthDegrees = 90.0, double Distance = 260.0, double HeightOffset = 8.0, double FieldOfView = 38.0, const FString& ActorLabel = "");

	/** Switches the live perspective viewport between Lit and Unlit for render-path diagnosis. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString SetViewportViewMode(const FString& ViewMode = "Lit");

	/** Sets one scalar parameter on a material instance and optionally saves the asset. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString SetMaterialScalarParameter(const FString& MaterialInstancePath, const FString& ParameterName, double Value, bool bSaveAsset = true);

	/** Sets one linear-color parameter on a material instance and optionally saves the asset. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString SetMaterialVectorParameter(const FString& MaterialInstancePath, const FString& ParameterName, double Red, double Green, double Blue, double Alpha = 1.0, bool bSaveAsset = true);

	/** Applies an overlay material to selected slots of a skeletal mesh component in the current editor world. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString SetCharacterOutlineOverlay(const FString& ActorLabel = "", const FString& OverlayMaterialPath = "", const FString& FaceOverlayMaterialPath = "", const FString& HairOverlayMaterialPath = "", const FString& ExcludedSlotIndices = "", const FString& FaceSlotIndices = "0", const FString& HairSlotIndices = "", double MaxDrawDistance = 6000.0, bool bSaveLevel = true);

	/** Enables custom depth on a character and installs an unbound depth-rim post-process material. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString SetCharacterDepthRim(const FString& ActorLabel = "", const FString& RimMaterialPath = "", int32 StencilValue = 1, double BlendWeight = 1.0, bool bSaveLevel = true);

	/** Schedules a high-resolution screenshot of the active editor viewport and returns the absolute output path. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|MCP")
	static FString CaptureEditorViewport(const FString& OutputFilename = "PMX4UE_MCP.png", int32 Width = 1200, int32 Height = 1200);

	UFUNCTION(BlueprintCallable, Category = "PMX4UE|Agent")
	static FString CaptureVisibleEditorViewport(const FString& OutputFilename = "PMX4UE_Visible.png", const FString& ActorLabel = "", const FString& CameraJson = "");

	/** Auto-frame or inspect the explicit subject in the same visible viewport used for capture. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|Preview")
	static FString FramePreviewSubject(const FString& ActorLabel, const FString& CameraJson, bool bApply = false);

	/** Requests full mips for the preview actor's used /Game textures and reports actual residency. */
	UFUNCTION(BlueprintCallable, Category = "PMX4UE|Agent")
	static FString CheckPreviewTextureResidency(const FString& ActorLabel, float HoldSeconds = 60.0f);
};
