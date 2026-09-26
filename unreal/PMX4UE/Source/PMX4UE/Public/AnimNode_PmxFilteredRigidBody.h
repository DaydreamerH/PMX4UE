#pragma once

#include "CoreMinimal.h"
#include "BoneControllers/AnimNode_RigidBody.h"
#include "AnimNode_PmxFilteredRigidBody.generated.h"

USTRUCT()
struct PMX4UE_API FPmxShapeFilter
{
    GENERATED_BODY()
    UPROPERTY() FName Bone;
    UPROPERTY() int32 ShapeIndex = 0;
    UPROPERTY() int32 Group = 0;
    UPROPERTY() int32 Mask = 0;
};

/** Stock UE RigidBody integration/constraints, with PMX per-shape collision masks.
 * No custom physics solver, bone construction, or mesh deformation code.
 * Isolated RBAN simulation without world geometry. Native UpdateInternal flushes
 * the previous deferred task before Evaluate; native InitPhysics flushes before
 * recreation. Filters are installed only before a new scene's first simulation.
 */
USTRUCT(BlueprintInternalUseOnly)
struct PMX4UE_API FAnimNode_PmxFilteredRigidBody : public FAnimNode_RigidBody
{
    GENERATED_BODY()
    UPROPERTY() TArray<FPmxShapeFilter> ShapeFilters;
    virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override;
    virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output, TArray<FBoneTransform>& OutBoneTransforms) override;
    int32 AppliedShapeFilters = 0;
    int32 FilterErrors = 0;
private:
    ImmediatePhysics::FSimulation* ConfiguredSimulation = nullptr;
    int32 ConfiguredActors = -1;
};
