#include "PMX4UEFaceSDFComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Materials/MaterialInstanceDynamic.h"

UPMX4UEFaceSDFComponent::UPMX4UEFaceSDFComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickGroup = TG_PostUpdateWork;
    bTickInEditor = true;
    bAutoActivate = true;
}

bool UPMX4UEFaceSDFComponent::ComputeBasis(const FQuat& ReferenceHead, const FQuat& CurrentHead,
    const FTransform& ComponentToWorld, const FVector& Forward, const FVector& Left,
    FVector& OutForward, FVector& OutLeft)
{
    if (ReferenceHead.ContainsNaN() || CurrentHead.ContainsNaN() || ComponentToWorld.ContainsNaN()
        || Forward.ContainsNaN() || Left.ContainsNaN()) return false;
    const FQuat Delta = CurrentHead.GetNormalized() * ReferenceHead.GetNormalized().Inverse();
    OutForward = ComponentToWorld.TransformVectorNoScale(Delta.RotateVector(Forward)).GetSafeNormal();
    OutLeft = ComponentToWorld.TransformVectorNoScale(Delta.RotateVector(Left));
    OutLeft = (OutLeft - OutForward * FVector::DotProduct(OutLeft, OutForward)).GetSafeNormal();
    return !OutForward.IsNearlyZero() && !OutLeft.IsNearlyZero();
}

void UPMX4UEFaceSDFComponent::ReleaseMaterials()
{
    if (USkeletalMeshComponent* Mesh = BoundMesh.Get())
    {
        if (FinalizedHandle.IsValid()) Mesh->UnregisterOnBoneTransformsFinalizedDelegate(FinalizedHandle);
        RemoveTickPrerequisiteComponent(Mesh);
        for (int32 I = 0; I < Instances.Num(); ++I)
        {
            if (Instances[I]) Instances[I]->SetScalarParameterValue(TEXT("FaceBasisRuntimeValid"), 0);
            if (Instances[I] && Mesh->GetMaterial(I) == Instances[I] && OriginalMaterials.IsValidIndex(I))
                Mesh->SetMaterial(I, OriginalMaterials[I]);
        }
    }
    Instances.Reset(); OriginalMaterials.Reset(); BoundMesh.Reset(); CachedAsset.Reset();
    FinalizedHandle.Reset();
    HeadIndex = INDEX_NONE; bBasisValid = false;
}

void UPMX4UEFaceSDFComponent::UpdateFaceParameters()
{
    if (BoundMesh.Get() != SourceMesh || (SourceMesh && CachedAsset.Get() != SourceMesh->GetSkeletalMeshAsset()))
    {
        ReleaseMaterials();
        BoundMesh = SourceMesh;
        if (SourceMesh)
        {
            AddTickPrerequisiteComponent(SourceMesh);
            // Also handle explicit editor pose evaluation and parallel animation completion.
            FinalizedHandle = SourceMesh->RegisterOnBoneTransformsFinalizedDelegate(
                FOnBoneTransformsFinalizedMultiCast::FDelegate::CreateUObject(this, &UPMX4UEFaceSDFComponent::UpdateFaceParameters));
        }
    }
    bBasisValid = false;
    if (!SourceMesh || !SourceMesh->GetSkeletalMeshAsset()) return;
    USkeletalMesh* Asset = SourceMesh->GetSkeletalMeshAsset();
    if (CachedAsset.Get() != Asset || CachedBone != HeadBone)
    {
        CachedAsset = Asset; CachedBone = HeadBone;
        const FReferenceSkeleton& Ref = Asset->GetRefSkeleton();
        HeadIndex = Ref.FindBoneIndex(HeadBone);
        if (HeadIndex != INDEX_NONE)
        {
            FTransform Reference = Ref.GetRefBonePose()[HeadIndex];
            for (int32 P = Ref.GetParentIndex(HeadIndex); P != INDEX_NONE; P = Ref.GetParentIndex(P))
                Reference *= Ref.GetRefBonePose()[P];
            ReferenceHeadRotation = Reference.GetRotation();
        }
    }
    const TArray<FTransform>& Pose = SourceMesh->GetComponentSpaceTransforms();
    if (Pose.IsValidIndex(HeadIndex))
        bBasisValid = ComputeBasis(ReferenceHeadRotation, Pose[HeadIndex].GetRotation(),
            SourceMesh->GetComponentTransform(), ReferenceForward, ReferenceLeft, FaceForwardWorld, FaceLeftWorld);

    const int32 Count = SourceMesh->GetNumMaterials();
    Instances.SetNum(Count); OriginalMaterials.SetNum(Count);
    for (int32 I = 0; I < Count; ++I)
    {
        UMaterialInterface* Material = SourceMesh->GetMaterial(I);
        if (Material != Instances[I] || !Instances[I])
        {
            Instances[I] = nullptr;
            float Contract = 0;
            // Only opt-in materials. Never write old FaceForwardWS/FaceLeftWS parameters.
            if (!Material || !Material->GetScalarParameterValue(FMaterialParameterInfo(TEXT("FaceBasisRuntimeValid")), Contract))
                continue;
            OriginalMaterials[I] = Material;
            Instances[I] = SourceMesh->CreateDynamicMaterialInstance(I, Material);
        }
        if (UMaterialInstanceDynamic* MID = Instances[I])
        {
            MID->SetScalarParameterValue(TEXT("FaceBasisRuntimeValid"), bBasisValid ? 1 : 0);
            if (bBasisValid)
            {
                MID->SetVectorParameterValue(TEXT("FaceForwardRuntimeWS"), FLinearColor(FaceForwardWorld));
                MID->SetVectorParameterValue(TEXT("FaceLeftRuntimeWS"), FLinearColor(FaceLeftWorld));
            }
        }
    }
}

void UPMX4UEFaceSDFComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* TickFunction)
{
    Super::TickComponent(DeltaTime, TickType, TickFunction);
    UpdateFaceParameters();
}

void UPMX4UEFaceSDFComponent::OnUnregister()
{
    ReleaseMaterials();
    Super::OnUnregister();
}
