#pragma once
#include "CoreMinimal.h"
#include "Animation/SkeletalMeshActor.h"
#include "PMX4UEFaceSDFPreviewActor.generated.h"

class UPMX4UEFaceSDFComponent;
class UAnimInstance;

/** Isolated preview integration. Not a replacement for a gameplay Character. */
UCLASS()
class PMX4UE_API APMX4UEFaceSDFPreviewActor : public ASkeletalMeshActor
{
    GENERATED_BODY()
public:
    APMX4UEFaceSDFPreviewActor();
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Face SDF")
    TObjectPtr<UPMX4UEFaceSDFComponent> FaceSDF;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Preview")
    TObjectPtr<USkeletalMesh> PreviewMesh;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Preview")
    TSubclassOf<UAnimInstance> PreviewAnimClass;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Preview")
    TObjectPtr<UMaterialInterface> FaceMaterial;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Preview")
    FName FaceSlot = TEXT("Face");
    virtual void OnConstruction(const FTransform& Transform) override;
};
