#include "PMX4UEWorkflowTools.h"
#include "AnimGraphNode_PmxFilteredRigidBody.h"
#include "AnimGraphNode_RigidBody.h"
#include "AnimGraphNode_SequencePlayer.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimClassInterface.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Animation/SkeletalMeshActor.h"
#include "Components/SkeletalMeshComponent.h"
#include "EditorAssetLibrary.h"
#include "Engine/Engine.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"
#include "Physics/ImmediatePhysics/ImmediatePhysicsSimulation.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/UnrealType.h"
#include "Editor.h"
#include "PlayInEditorDataTypes.h"
#include "Settings/LevelEditorPlaySettings.h"
#include "Engine/GameViewportClient.h"
#include "Slate/SceneViewport.h"

bool UPMX4UEWorkflowTools::SetPreviewResolution(int32 Width,int32 Height)
{
    if (!GEditor || !GEditor->PlayWorld || Width<64 || Height<64 || Width>7680 || Height>4320) return false;
    auto* Context=GEngine->GetWorldContextFromWorld(GEditor->PlayWorld);
    if (!Context || !Context->GameViewport || !Context->GameViewport->GetGameViewport()) return false;
    Context->GameViewport->GetGameViewport()->SetFixedViewportSize(Width,Height);
    return true;
}

bool UPMX4UEWorkflowTools::BeginPreviewWindow(int32 Width,int32 Height)
{
    if (!GEditor || GEditor->PlayWorld || Width<64 || Height<64 || Width>7680 || Height>4320) return false;
    auto* Settings=DuplicateObject<ULevelEditorPlaySettings>(GetDefault<ULevelEditorPlaySettings>(),GetTransientPackage());
    Settings->NewWindowWidth=Width; Settings->NewWindowHeight=Height;
    FRequestPlaySessionParams Params;
    Params.EditorPlaySettings=Settings;
    Params.WorldType=EPlaySessionWorldType::PlayInEditor;
    GEditor->RequestPlaySession(Params);
    return true;
}

namespace WorkflowProbe
{
FString Json(const TSharedRef<FJsonObject>& R)
{
    FString Out; FJsonSerializer::Serialize(R, TJsonWriterFactory<>::Create(&Out)); return Out;
}
FString Fail(const FString& Message)
{
    auto R=MakeShared<FJsonObject>(); R->SetStringField(TEXT("error"),Message); return Json(R);
}
TSharedRef<FJsonObject> Settings(const FAnimNode_RigidBody& N)
{
    auto R=MakeShared<FJsonObject>();
    R->SetStringField(TEXT("physics_asset"),GetPathNameSafe(N.OverridePhysicsAsset));
    R->SetNumberField(TEXT("space"),int32(N.SimulationSpace));
    R->SetStringField(TEXT("base_bone"),N.BaseBoneRef.BoneName.ToString());
    R->SetNumberField(TEXT("world_alpha"),N.SimSpaceSettings.WorldAlpha);
    R->SetNumberField(TEXT("damping_alpha"),N.SimSpaceSettings.DampingAlpha);
    R->SetNumberField(TEXT("max_linear_acceleration"),N.SimSpaceSettings.MaxLinearAcceleration);
    R->SetNumberField(TEXT("max_linear_velocity"),N.SimSpaceSettings.MaxLinearVelocity);
    R->SetNumberField(TEXT("max_angular_velocity"),N.SimSpaceSettings.MaxAngularVelocity);
    R->SetNumberField(TEXT("max_angular_acceleration"),N.SimSpaceSettings.MaxAngularAcceleration);
    R->SetNumberField(TEXT("timing"),int32(N.SimulationTiming));
    if (N.OverridePhysicsAsset)
    {
        R->SetNumberField(TEXT("fixed_step"),N.OverridePhysicsAsset->SolverSettings.FixedTimeStep);
        R->SetNumberField(TEXT("iterations"),N.OverridePhysicsAsset->SolverSettings.PositionIterations);
    }
    return R;
}
}


FString UPMX4UEWorkflowTools::ConfigurePhysicsBlueprint(const FString& BlueprintPath,const FString& SettingsJson)
{
    using namespace WorkflowProbe;
    TSharedPtr<FJsonObject> J;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(SettingsJson),J) || !J.IsValid()) return Fail(TEXT("Invalid settings JSON"));
    FString Space,Base,Timing;
    double World=0,Damping=0,LV=0,LA=0,AV=0,AA=0;
    if (!J->TryGetStringField(TEXT("space"),Space) || !J->TryGetStringField(TEXT("base_bone"),Base)
        || !J->TryGetStringField(TEXT("timing"),Timing)
        || !J->TryGetNumberField(TEXT("world_alpha"),World) || !J->TryGetNumberField(TEXT("damping_alpha"),Damping)
        || !J->TryGetNumberField(TEXT("max_linear_velocity"),LV) || !J->TryGetNumberField(TEXT("max_linear_acceleration"),LA)
        || !J->TryGetNumberField(TEXT("max_angular_velocity"),AV) || !J->TryGetNumberField(TEXT("max_angular_acceleration"),AA))
        return Fail(TEXT("Missing explicit simulation settings"));
    for (double V:{World,Damping,LV,LA,AV,AA}) if (!FMath::IsFinite(V) || V<0) return Fail(TEXT("Invalid simulation number"));
    if (World>1 || Damping>1 || (Space!=TEXT("component") && Space!=TEXT("base_bone") && Space!=TEXT("world"))
        || (Timing!=TEXT("deferred") && Timing!=TEXT("synchronous"))) return Fail(TEXT("Invalid simulation enum/range"));
    auto* BP=LoadObject<UAnimBlueprint>(nullptr,*BlueprintPath);
    if (!BP || !BP->GetPreviewMesh()) return Fail(TEXT("Missing blueprint/preview mesh"));
    if (Space==TEXT("base_bone") && (Base.IsEmpty() || BP->GetPreviewMesh()->GetRefSkeleton().FindBoneIndex(FName(*Base))<0))
        return Fail(TEXT("Invalid base bone"));
    TArray<UEdGraph*> Graphs; BP->GetAllGraphs(Graphs);
    TArray<FAnimNode_RigidBody*> Nodes;
    for (auto* G:Graphs) for (UEdGraphNode* Node:G->Nodes)
    {
        if (auto* F=Cast<UAnimGraphNode_PmxFilteredRigidBody>(Node)) Nodes.Add(&F->Node);
        else if (auto* N=Cast<UAnimGraphNode_RigidBody>(Node)) Nodes.Add(&N->Node);
    }
    for (auto* N:Nodes) if (Space==TEXT("base_bone") && N->OverridePhysicsAsset)
        for (USkeletalBodySetup* B:N->OverridePhysicsAsset->SkeletalBodySetups)
            if (B && B->BoneName==FName(*Base) && B->PhysicsType==PhysType_Simulated) return Fail(TEXT("Base bone must not be simulated"));
    TArray<TSharedPtr<FJsonValue>> Values;
    for (auto* N:Nodes)
    {
        N->SimulationSpace=Space==TEXT("base_bone")?ESimulationSpace::BaseBoneSpace:Space==TEXT("world")?ESimulationSpace::WorldSpace:ESimulationSpace::ComponentSpace;
        N->BaseBoneRef.BoneName=Space==TEXT("base_bone")?FName(*Base):NAME_None;
        N->SimSpaceSettings.WorldAlpha=World; N->SimSpaceSettings.DampingAlpha=Damping;
        N->SimSpaceSettings.MaxLinearVelocity=LV; N->SimSpaceSettings.MaxLinearAcceleration=LA;
        N->SimSpaceSettings.MaxAngularVelocity=AV; N->SimSpaceSettings.MaxAngularAcceleration=AA;
        N->SimulationTiming=Timing==TEXT("deferred")?ESimulationTiming::Deferred:ESimulationTiming::Synchronous;
        Values.Add(MakeShared<FJsonValueObject>(Settings(*N)));
    }
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP);
    FKismetEditorUtilities::CompileBlueprint(BP);
    if (!BP->GeneratedClass || BP->Status==BS_Error || !UEditorAssetLibrary::SaveLoadedAsset(BP,false)) return Fail(TEXT("Compile/save failed"));
    auto R=MakeShared<FJsonObject>(); R->SetStringField(TEXT("status"),TEXT("configured")); R->SetArrayField(TEXT("nodes"),Values); return Json(R);
}

FString UPMX4UEWorkflowTools::TestMotion(const FString& MeshPath,const FString& BlueprintPath,
    float Seconds,float FramesPerSecond,bool bHitches,bool bMoveComponent,const FString& MeasurementAnchor,const TArray<FString>& MeasurementBones)
{
    using namespace WorkflowProbe;
    auto* Mesh=LoadObject<USkeletalMesh>(nullptr,*MeshPath);
    auto* BP=LoadObject<UAnimBlueprint>(nullptr,*BlueprintPath);
    if (!Mesh || !BP || !BP->GeneratedClass || Seconds<3 || Seconds>30 || FramesPerSecond<15 || FramesPerSecond>200)
        return Fail(TEXT("Invalid test inputs"));
    const auto& Ref=Mesh->GetRefSkeleton(); const int32 Anchor=Ref.FindBoneIndex(FName(*MeasurementAnchor));
    if (Anchor<0 || BP->TargetSkeleton!=Mesh->GetSkeleton() || MeasurementBones.IsEmpty()) return Fail(TEXT("Missing measurement anchor/bones or skeleton mismatch"));
    TSet<FName> Measured;
    for (const FString& Name:MeasurementBones)
    {
        if (Ref.FindBoneIndex(FName(*Name))<0) return Fail(TEXT("Missing measurement bone: ")+Name);
        Measured.Add(FName(*Name));
    }
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(true)
        .CreateNavigation(false).CreateAISystem(false).ShouldSimulatePhysics(false).SetTransactional(false);
    auto* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    auto* Actor=World->SpawnActor<ASkeletalMeshActor>(); auto* Body=Actor->GetSkeletalMeshComponent();
    Body->SetSkeletalMesh(Mesh); Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Body->SetAnimationMode(EAnimationMode::AnimationBlueprint); Body->SetAnimInstanceClass(BP->GeneratedClass);
    Body->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    Body->bEnableUpdateRateOptimizations=false; Body->SetComponentTickEnabled(false);
    World->InitializeActorsForPlay(FURL()); World->BeginPlay();
    // Deliberately retain authored root/pelvis displacement. Unlike TestExperiment,
    // this exercises the moving skeleton and loop discontinuities seen in preview.
    Body->GetAnimInstance()->SetRootMotionMode(ERootMotionMode::NoRootMotionExtraction);
    TArray<FAnimNode_RigidBody*> Nodes; TArray<FAnimNode_PmxFilteredRigidBody*> FilteredNodes; TSet<FName> Simulated;
    auto* Instance=Body->GetAnimInstance();
    for (auto* Property:IAnimClassInterface::GetFromClass(Instance->GetClass())->GetAnimNodeProperties())
        if (Property->Struct->IsChildOf(FAnimNode_RigidBody::StaticStruct()))
        {
            auto* N=Property->ContainerPtrToValuePtr<FAnimNode_RigidBody>(Instance); Nodes.Add(N);
            if (Property->Struct==FAnimNode_PmxFilteredRigidBody::StaticStruct())
                FilteredNodes.Add(Property->ContainerPtrToValuePtr<FAnimNode_PmxFilteredRigidBody>(Instance));
            if (N->OverridePhysicsAsset) for (USkeletalBodySetup* S:N->OverridePhysicsAsset->SkeletalBodySetups)
                if (S->PhysicsType==PhysType_Simulated) Simulated.Add(S->BoneName);
        }
    TArray<FTransform> Rest=Ref.GetRefBonePose();
    for (int32 I=1;I<Rest.Num();++I) Rest[I]*=Rest[Ref.GetParentIndex(I)];
    TArray<int32> Indices; for (int32 I=0;I<Ref.GetNum();++I) if (Simulated.Contains(Ref.GetBoneName(I))) Indices.Add(I);
    TArray<TSharedPtr<FJsonValue>> Samples; TArray<FVector> Previous; TArray<double> Timings;
    bool Finite=true; double Time=0; int32 Frame=0; double MaxEdge=1,MaxRadius=0;
    while (Time<Seconds && Finite)
    {
        const float NominalDt=bHitches && Frame%45==44?0.1f:1.f/FramesPerSecond;
        // Do not manufacture a microsecond final frame from floating-point residue.
        // Such a frame corrupts velocity/acceleration estimates and is not a low-FPS case.
        if (Seconds-Time<1.e-4) break;
        const float Dt=float(Seconds-Time < double(NominalDt)*1.05 ? Seconds-Time : double(NominalDt));
        if (bMoveComponent) Actor->SetActorLocationAndRotation(FVector(300.f*Time,0,0),FRotator(0,20.f*FMath::Sin(Time),0));
        ++GFrameCounter; World->Tick(LEVELTICK_All,Dt);
        const double Start=FPlatformTime::Seconds(); Body->TickAnimation(Dt,false); Body->RefreshBoneTransforms();
        if (Time>=2) Timings.Add((FPlatformTime::Seconds()-Start)*1000);
        const auto& Current=Body->GetComponentSpaceTransforms();
        if (Current.Num()!=Rest.Num()) { Finite=false; break; }
        FVector Centroid=FVector::ZeroVector; int32 Skirts=0; double Step=0,Edge=1,Radius=0;
        TArray<FVector> Now;
        for (int32 I:Indices)
        {
            if (Current[I].ContainsNaN()) { Finite=false; break; }
            const FVector P=Current[Anchor].InverseTransformPosition(Current[I].GetLocation()); Now.Add(P);
            if (Previous.Num()==Indices.Num()) Step=FMath::Max(Step,(P-Previous[Now.Num()-1]).Size());
            const int32 Parent=Ref.GetParentIndex(I);
            const double Length=Parent>=0?(Rest[I].GetLocation()-Rest[Parent].GetLocation()).Size():0;
            if (Length>0.1) Edge=FMath::Max(Edge,(Current[I].GetLocation()-Current[Parent].GetLocation()).Size()/Length);
            if (Measured.Contains(Ref.GetBoneName(I))) { Centroid+=P; ++Skirts; Radius=FMath::Max(Radius,P.Size()); }
        }
        if (Skirts) Centroid/=Skirts;
        auto S=MakeShared<FJsonObject>(); S->SetNumberField(TEXT("time"),Time+Dt); S->SetNumberField(TEXT("dt"),Dt);
        S->SetNumberField(TEXT("edge_ratio"),Edge); S->SetNumberField(TEXT("step_cm"),Step); S->SetNumberField(TEXT("measurement_radius_cm"),Radius);
        S->SetStringField(TEXT("anchor_component"),Current[Anchor].GetLocation().ToString());
        S->SetArrayField(TEXT("measurement_centroid"),{MakeShared<FJsonValueNumber>(Centroid.X),MakeShared<FJsonValueNumber>(Centroid.Y),MakeShared<FJsonValueNumber>(Centroid.Z)});
        Samples.Add(MakeShared<FJsonValueObject>(S)); Previous=MoveTemp(Now); MaxEdge=FMath::Max(MaxEdge,Edge); MaxRadius=FMath::Max(MaxRadius,Radius);
        Time+=Dt; ++Frame; if (Radius>500) break;
    }
    int32 Errors=0,Filters=0; TArray<TSharedPtr<FJsonValue>> Runtime;
    for (auto* N:Nodes) Runtime.Add(MakeShared<FJsonValueObject>(Settings(*N)));
    for (auto* N:FilteredNodes) { Errors+=N->FilterErrors; Filters+=N->AppliedShapeFilters; }
    Timings.Sort(); double Mean=0; for (double Ms:Timings) Mean+=Ms;
    auto R=MakeShared<FJsonObject>(); R->SetStringField(TEXT("status"),Finite && Time>=Seconds-1.e-4 && Indices.Num()>0 && Errors==0?TEXT("measured"):TEXT("failed")); R->SetBoolField(TEXT("finite"),Finite); R->SetNumberField(TEXT("seconds_completed"),Time);
    R->SetNumberField(TEXT("frames"),Frame); R->SetNumberField(TEXT("simulated_bones"),Indices.Num()); R->SetNumberField(TEXT("filter_errors"),Errors);
    R->SetNumberField(TEXT("filters_applied"),Filters); R->SetNumberField(TEXT("max_edge_ratio"),MaxEdge); R->SetNumberField(TEXT("max_measurement_radius_cm"),MaxRadius);
    R->SetArrayField(TEXT("samples"),Samples); R->SetArrayField(TEXT("nodes"),Runtime);
    if (Timings.Num()) { R->SetNumberField(TEXT("evaluation_mean_ms"),Mean/Timings.Num()); R->SetNumberField(TEXT("evaluation_p99_ms"),Timings[FMath::Min(Timings.Num()-1,FMath::FloorToInt(Timings.Num()*.99))]); }
    R->SetStringField(TEXT("scope"),TEXT("Synthetic dt, unextracted animation displacement; optional continuous component motion; no periodic resets; not rendered FPS or CharacterMovement root extraction"));
    Actor->Destroy(); GEngine->DestroyWorldContext(World); World->DestroyWorld(false); return Json(R);
}
