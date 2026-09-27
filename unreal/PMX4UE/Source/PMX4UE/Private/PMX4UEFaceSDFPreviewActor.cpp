#include "PMX4UEFaceSDFPreviewActor.h"
#include "PMX4UEFaceSDFComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Animation/AnimInstance.h"

APMX4UEFaceSDFPreviewActor::APMX4UEFaceSDFPreviewActor()
{
    FaceSDF = CreateDefaultSubobject<UPMX4UEFaceSDFComponent>(TEXT("FaceSDF"));
    FaceSDF->SourceMesh = GetSkeletalMeshComponent();
}

void APMX4UEFaceSDFPreviewActor::OnConstruction(const FTransform& Transform)
{
    Super::OnConstruction(Transform);
    USkeletalMeshComponent* Mesh = GetSkeletalMeshComponent();
    if (PreviewMesh) Mesh->SetSkeletalMesh(PreviewMesh);
    if (PreviewAnimClass)
    {
        Mesh->SetAnimationMode(EAnimationMode::AnimationBlueprint);
        Mesh->SetAnimInstanceClass(PreviewAnimClass);
        if (Mesh->GetAnimInstance()) Mesh->GetAnimInstance()->SetRootMotionMode(ERootMotionMode::NoRootMotionExtraction);
    }
    const int32 Slot = Mesh->GetMaterialIndex(FaceSlot);
    if (FaceMaterial && Slot != INDEX_NONE) Mesh->SetMaterial(Slot, FaceMaterial);
    FaceSDF->SourceMesh = Mesh;
    FaceSDF->UpdateFaceParameters();
}
