#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "PMX4UEFaceSDFComponent.generated.h"

class USkeletalMeshComponent;
class USkeletalMesh;
class UMaterialInstanceDynamic;
class UMaterialInterface;

/** Per-character face basis, sampled AFTER animation. Does not alter bones or locomotion. */
UCLASS(ClassGroup=(PMX4UE), meta=(BlueprintSpawnableComponent))
class PMX4UE_API UPMX4UEFaceSDFComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UPMX4UEFaceSDFComponent();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Face SDF")
    TObjectPtr<USkeletalMeshComponent> SourceMesh;

    // Explicit model mapping; no character-specific bone name in generic defaults.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Face SDF")
    FName HeadBone = NAME_None;

    // Model/component-space face axes in the IMPORTED REFERENCE pose, not bone-local axes.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Face SDF")
    FVector ReferenceForward = FVector(0, 1, 0);

    // Keep the material's SDF hemisphere convention (some maps call +X "left").
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Face SDF")
    FVector ReferenceLeft = FVector(1, 0, 0);

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="Face SDF")
    FVector FaceForwardWorld = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="Face SDF")
    FVector FaceLeftWorld = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="Face SDF")
    bool bBasisValid = false;

    // Optional hair output shares the SAME post-animation head sampling.
    // Positions and axes below are imported REFERENCE component-space values.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Head Hair")
    bool bDriveHair = false;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Head Hair")
    TArray<int32> HairMaterialSlots;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Head Hair")
    FVector ReferenceHairUp = FVector(0, 0, 1);

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Head Hair")
    FVector HairSphereCenterReferenceCS = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="Head Hair")
    FVector HairUpWorld = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="Head Hair")
    FVector HairSphereCenterWorld = FVector::ZeroVector;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category="Head Hair")
    bool bHairBasisValid = false;

    static bool ComputeHairBasis(const FTransform& ReferenceHead, const FTransform& CurrentHead,
        const FTransform& ComponentToWorld, const FVector& ReferenceUp, const FVector& ReferenceCenter,
        FVector& OutUp, FVector& OutCenter);

    /** Useful after explicit pose evaluation in editor tools; normal play updates automatically. */
    UFUNCTION(BlueprintCallable, Category="Face SDF")
    void UpdateFaceParameters();

    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    virtual void OnUnregister() override;

    /** Ref-pose calibration avoids assuming that a Head bone's +X is the face forward. */
    static bool ComputeBasis(const FQuat& ReferenceHead, const FQuat& CurrentHead,
        const FTransform& ComponentToWorld, const FVector& Forward, const FVector& Left,
        FVector& OutForward, FVector& OutLeft);

private:
    void ReleaseMaterials();
    TWeakObjectPtr<USkeletalMeshComponent> BoundMesh;
    TWeakObjectPtr<USkeletalMesh> CachedAsset;
    FName CachedBone;
    int32 HeadIndex = INDEX_NONE;
    FQuat ReferenceHeadRotation = FQuat::Identity;
    FTransform ReferenceHeadTransform = FTransform::Identity;
    FDelegateHandle FinalizedHandle;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> Instances;
    UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInterface>> OriginalMaterials;
};
