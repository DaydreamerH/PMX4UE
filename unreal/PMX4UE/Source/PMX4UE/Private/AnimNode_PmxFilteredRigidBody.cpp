#include "AnimNode_PmxFilteredRigidBody.h"
#include "Chaos/Collision/CollisionContext.h"
#include "Chaos/CollisionFilterData.h"
#include "Chaos/ParticleHandle.h"
#include "Physics/ImmediatePhysics/ImmediatePhysicsActorHandle.h"
#include "Physics/ImmediatePhysics/ImmediatePhysicsSimulation.h"

void FAnimNode_PmxFilteredRigidBody::Initialize_AnyThread(const FAnimationInitializeContext& Context)
{
    ConfiguredSimulation = nullptr;
    ConfiguredActors = -1;
    AppliedShapeFilters = FilterErrors = 0;
    FAnimNode_RigidBody::Initialize_AnyThread(Context);
}

void FAnimNode_PmxFilteredRigidBody::EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output, TArray<FBoneTransform>& OutBoneTransforms)
{
    auto* Simulation = GetSimulation();
    if (Simulation && (Simulation != ConfiguredSimulation || Simulation->NumActors() != ConfiguredActors))
    {
        AppliedShapeFilters = 0;
        FilterErrors = 0;
        TMap<FName, ImmediatePhysics::FActorHandle*> Actors;
        int32 ShapeCount = 0;
        for (int32 I = 0; I < Simulation->NumActors(); ++I)
        {
            auto* Actor = Simulation->GetActorHandle(I);
            Actors.Add(Actor->GetName(), Actor);
            ShapeCount += Actor->GetParticle()->ShapesArray().Num();
        }
        for (const auto& Row : ShapeFilters)
        {
            auto** Found = Actors.Find(Row.Bone);
            if (!Found || !(*Found)->GetParticle()->ShapesArray().IsValidIndex(Row.ShapeIndex))
            {
                ++FilterErrors;
                continue;
            }
            auto& Shape = (*Found)->GetParticle()->ShapesArray()[Row.ShapeIndex];
            const auto Filter = Chaos::Filter::FShapeFilterBuilder()
                .SetCollisionChannelIndex(uint8(Row.Group))
                .SetBlockChannelMask(uint64(Row.Mask))
                .SetOverlapChannelMask(0)
                .SetFilterFlags(Chaos::EFilterFlags::All).Build();
            Chaos::FCollisionData Data;
            Data.SetShapeFilterData(Filter);
            Data.bSimCollision = 1;
            Data.bQueryCollision = 0;
            Shape->SetCollisionData(Data);
            if (Shape->GetShapeFilterData().GetCollisionChannelIndex()!=Row.Group || Shape->GetShapeFilterData().GetBlockChannels()!=uint64(Row.Mask)) ++FilterErrors;
            ++AppliedShapeFilters;
        }
        if (ShapeCount != AppliedShapeFilters) ++FilterErrors;
        auto Settings = Simulation->GetCollisionDetectorSettings();
        Settings.bFilteringEnabled = true;
        Simulation->SetCollisionDetectorSettings(Settings);
        ConfiguredSimulation = Simulation;
        ConfiguredActors = Simulation->NumActors();
        ensureMsgf(FilterErrors == 0, TEXT("PMX shape filter mapping mismatch; physics output disabled"));
    }
    // Never run an accidentally unfiltered full-character collision setup.
    if (FilterErrors == 0)
        FAnimNode_RigidBody::EvaluateSkeletalControl_AnyThread(Output, OutBoneTransforms);
}
