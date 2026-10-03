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

bool UPMX4UEFaceSDFComponent::ComputeHairBasis(const FTransform& ReferenceHead, const FTransform& CurrentHead,
    const FTransform& ComponentToWorld, const FVector& ReferenceUp, const FVector& ReferenceCenter,
    FVector& OutUp, FVector& OutCenter)
{
    if (ReferenceHead.ContainsNaN() || CurrentHead.ContainsNaN() || ComponentToWorld.ContainsNaN()
        || ReferenceUp.ContainsNaN() || ReferenceCenter.ContainsNaN()
        || ReferenceHead.GetScale3D().GetAbsMin() <= SMALL_NUMBER) return false;
    const FQuat Delta = CurrentHead.GetRotation().GetNormalized()
        * ReferenceHead.GetRotation().GetNormalized().Inverse();
    OutUp = ComponentToWorld.TransformVectorNoScale(Delta.RotateVector(ReferenceUp)).GetSafeNormal();
    OutCenter = ComponentToWorld.TransformPosition(CurrentHead.TransformPosition(
        ReferenceHead.InverseTransformPosition(ReferenceCenter)));
    return !OutUp.IsNearlyZero() && !OutUp.ContainsNaN() && !OutCenter.ContainsNaN();
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
            if (Instances[I]) Instances[I]->SetScalarParameterValue(TEXT("HairBasisRuntimeValid"), 0);
            if (Instances[I] && Mesh->GetMaterial(I) == Instances[I] && OriginalMaterials.IsValidIndex(I))
                Mesh->SetMaterial(I, OriginalMaterials[I]);
        }
    }
    Instances.Reset(); OriginalMaterials.Reset(); BoundMesh.Reset(); CachedAsset.Reset();
    FinalizedHandle.Reset();
    HeadIndex = INDEX_NONE; bBasisValid = false; bHairBasisValid = false;
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
    bHairBasisValid = false;
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
            ReferenceHeadTransform = Reference;
        }
    }
    const TArray<FTransform>& Pose = SourceMesh->GetComponentSpaceTransforms();
    if (Pose.IsValidIndex(HeadIndex))
    {
        bBasisValid = ComputeBasis(ReferenceHeadRotation, Pose[HeadIndex].GetRotation(),
            SourceMesh->GetComponentTransform(), ReferenceForward, ReferenceLeft, FaceForwardWorld, FaceLeftWorld);
        if (bDriveHair)
            bHairBasisValid = ComputeHairBasis(ReferenceHeadTransform, Pose[HeadIndex],
                SourceMesh->GetComponentTransform(), ReferenceHairUp, HairSphereCenterReferenceCS,
                HairUpWorld, HairSphereCenterWorld);
    }

    const int32 Count = SourceMesh->GetNumMaterials();
    Instances.SetNum(Count); OriginalMaterials.SetNum(Count);
    for (int32 I = 0; I < Count; ++I)
    {
        UMaterialInterface* Material = SourceMesh->GetMaterial(I);
        float Contract = 0;
        const bool FaceOptIn = Material && Material->GetScalarParameterValue(
            FMaterialParameterInfo(TEXT("FaceBasisRuntimeValid")), Contract);
        const bool HairOptIn = bDriveHair && HairMaterialSlots.Contains(I) && Material
            && Material->GetScalarParameterValue(FMaterialParameterInfo(TEXT("HairBasisRuntimeValid")), Contract);
        if (!FaceOptIn && !HairOptIn)
        {
            if (Instances[I] && Material == Instances[I] && OriginalMaterials.IsValidIndex(I))
            {
                Instances[I]->SetScalarParameterValue(TEXT("HairBasisRuntimeValid"), 0);
                SourceMesh->SetMaterial(I, OriginalMaterials[I]);
            }
            Instances[I] = nullptr;
            continue;
        }
        if (Material != Instances[I] || !Instances[I])
        {
            Instances[I] = nullptr;
            // Only opt-in materials. Never write old FaceForwardWS/FaceLeftWS parameters.
            OriginalMaterials[I] = Material;
            Instances[I] = SourceMesh->CreateDynamicMaterialInstance(I, Material);
        }
        if (UMaterialInstanceDynamic* MID = Instances[I])
        {
            if (FaceOptIn) MID->SetScalarParameterValue(TEXT("FaceBasisRuntimeValid"), bBasisValid ? 1 : 0);
            if (FaceOptIn && bBasisValid)
            {
                MID->SetVectorParameterValue(TEXT("FaceForwardRuntimeWS"), FLinearColor(FaceForwardWorld));
                MID->SetVectorParameterValue(TEXT("FaceLeftRuntimeWS"), FLinearColor(FaceLeftWorld));
            }
            MID->SetScalarParameterValue(TEXT("HairBasisRuntimeValid"), HairOptIn && bHairBasisValid ? 1 : 0);
            if (HairOptIn && bHairBasisValid)
            {
                MID->SetVectorParameterValue(TEXT("HairUpRuntimeWS"), FLinearColor(HairUpWorld));
                MID->SetVectorParameterValue(TEXT("HeadSphereCenterWS"), FLinearColor(HairSphereCenterWorld));
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
