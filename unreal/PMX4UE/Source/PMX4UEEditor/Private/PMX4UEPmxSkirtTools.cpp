#include "PMX4UEPmxSkirtTools.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AnimGraphNode_Root.h"
#include "AnimGraphNode_SequencePlayer.h"
#include "AnimGraphNode_LocalRefPose.h"
#include "AnimGraphNode_LocalToComponentSpace.h"
#include "AnimGraphNode_ComponentToLocalSpace.h"
#include "AnimGraphNode_RigidBody.h"
#include "AnimGraphNode_PmxFilteredRigidBody.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimClassInterface.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimData/IAnimationDataModel.h"
#include "Animation/AnimData/IAnimationDataController.h"
#include "AnimationGraphSchema.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/SkeletalMesh.h"
#include "Animation/SkeletalMeshActor.h"
#include "Engine/World.h"
#include "EditorAssetLibrary.h"
#include "Factories/AnimBlueprintFactory.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/PhysicsConstraintTemplate.h"
#include "PhysicsEngine/SkeletalBodySetup.h"
#include "Physics/ImmediatePhysics/ImmediatePhysicsSimulation.h"
#include "Physics/ImmediatePhysics/ImmediatePhysicsActorHandle.h"
#include "Chaos/ParticleHandle.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/Package.h"
#include "UObject/UnrealType.h"

namespace PmxSkirt
{
FString Json(const TSharedRef<FJsonObject>& R)
{
    FString Out;
    FJsonSerializer::Serialize(R, TJsonWriterFactory<>::Create(&Out));
    return Out;
}
FString Fail(const FString& Message)
{
    auto R = MakeShared<FJsonObject>();
    R->SetStringField(TEXT("status"), TEXT("error"));
    R->SetStringField(TEXT("message"), Message);
    UE_LOG(LogTemp, Error, TEXT("PMX skirt: %s"), *Message);
    return Json(R);
}
FVector Vec(const TSharedPtr<FJsonObject>& O, const TCHAR* Key)
{
    const auto& A = O->GetArrayField(Key);
    return FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber());
}
FQuat Quat(const TSharedPtr<FJsonObject>& O)
{
    const auto& A = O->GetArrayField(TEXT("rotation_blender_xyzw"));
    return FQuat(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber(), A[3]->AsNumber()).GetNormalized();
}
TArray<FTransform> Rest(USkeletalMesh* Mesh)
{
    const auto& Ref = Mesh->GetRefSkeleton();
    TArray<FTransform> Pose = Ref.GetRefBonePose();
    for (int32 I = 0; I < Pose.Num(); ++I)
        if (Ref.GetParentIndex(I) >= 0) Pose[I] *= Pose[Ref.GetParentIndex(I)];
    return Pose;
}
// Align positions only; units are explicitly meters->centimeters, never fitted.
// Retain Blender local shape/joint axes. A reflected coordinate basis is made
// right handed by flipping local X (not by conjugating a box's orientation).
struct FBasis
{
    int32 P[3] = {0,1,2}, S[3] = {1,1,1};
    FVector Offset = FVector::ZeroVector;
    double Error = BIG_NUMBER;
    FVector Map(const FVector& V) const { return FVector(S[0]*V[P[0]], S[1]*V[P[1]], S[2]*V[P[2]]); }
    double Hand() const { return FVector::DotProduct(FVector::CrossProduct(Map(FVector::XAxisVector), Map(FVector::YAxisVector)), Map(FVector::ZAxisVector)); }
    FTransform Frame(const TSharedPtr<FJsonObject>& O) const
    {
        const FQuat Q = Quat(O);
        FMatrix M = FMatrix::Identity;
        M.SetAxis(0, Hand()*Map(Q.RotateVector(FVector::XAxisVector)));
        M.SetAxis(1, Map(Q.RotateVector(FVector::YAxisVector)));
        M.SetAxis(2, Map(Q.RotateVector(FVector::ZAxisVector)));
        return FTransform(FQuat(M).GetNormalized(), Map(Vec(O,TEXT("position_blender_m")))*100.0+Offset);
    }
};
FBasis Fit(const TArray<TSharedPtr<FJsonValue>>& Landmarks, USkeletalMesh* Mesh, const TArray<FTransform>& Pose)
{
    FBasis Best;
    const int32 Permutations[6][3]={{0,1,2},{0,2,1},{1,0,2},{1,2,0},{2,0,1},{2,1,0}};
    for (const auto& P : Permutations) for (int32 Mask=0; Mask<8; ++Mask)
    {
        FBasis B;
        for (int32 A=0; A<3; ++A) { B.P[A]=P[A]; B.S[A]=(Mask&(1<<A))?-1:1; }
        for (const auto& L : Landmarks)
        {
            const auto O=L->AsObject();
            const int32 I=Mesh->GetRefSkeleton().FindBoneIndex(FName(*O->GetStringField(TEXT("target_bone"))));
            if (I<0) return Best;
            B.Offset+=Pose[I].GetLocation()-100.0*B.Map(Vec(O,TEXT("position_blender_m")));
        }
        B.Offset/=Landmarks.Num(); B.Error=0;
        for (const auto& L : Landmarks)
        {
            const auto O=L->AsObject();
            const int32 I=Mesh->GetRefSkeleton().FindBoneIndex(FName(*O->GetStringField(TEXT("target_bone"))));
            B.Error+=(Pose[I].GetLocation()-100.0*B.Map(Vec(O,TEXT("position_blender_m")))-B.Offset).SizeSquared();
        }
        B.Error=FMath::Sqrt(B.Error/Landmarks.Num());
        if (B.Error<Best.Error) Best=B;
    }
    return Best;
}
FString Pair(FName A, FName B)
{
    FString X=A.ToString(), Y=B.ToString();
    return X<Y ? X+TEXT("|")+Y : Y+TEXT("|")+X;
}
bool Save(UObject* Object)
{
    FAssetRegistryModule::AssetCreated(Object);
    Object->MarkPackageDirty();
    return UEditorAssetLibrary::SaveLoadedAsset(Object, false);
}
}

FString UPMX4UEPmxSkirtTools::InspectPhysicsMesh(const FString& MeshPath)
{
    using namespace PmxSkirt;
    auto* Mesh=LoadObject<USkeletalMesh>(nullptr,*MeshPath);
    if (!Mesh || !Mesh->GetSkeleton()) return Fail(TEXT("missing mesh or skeleton"));
    auto R=MakeShared<FJsonObject>(); R->SetStringField(TEXT("status"),TEXT("inspected"));
    R->SetStringField(TEXT("mesh"),MeshPath); R->SetStringField(TEXT("skeleton"),Mesh->GetSkeleton()->GetPathName());
    const auto Pose=Rest(Mesh); const auto& Ref=Mesh->GetRefSkeleton();
    TArray<TSharedPtr<FJsonValue>> Bones;
    for (int32 I=0; I<Pose.Num(); ++I)
    {
        auto B=MakeShared<FJsonObject>(); B->SetStringField(TEXT("name"),Ref.GetBoneName(I).ToString());
        const int32 Parent=Ref.GetParentIndex(I);
        B->SetStringField(TEXT("parent"),Parent>=0?Ref.GetBoneName(Parent).ToString():TEXT(""));
        TArray<TSharedPtr<FJsonValue>> Scale,Position;
        for (int32 A=0; A<3; ++A)
        {
            Scale.Add(MakeShared<FJsonValueNumber>(Pose[I].GetScale3D()[A]));
            Position.Add(MakeShared<FJsonValueNumber>(Pose[I].GetLocation()[A]));
        }
        B->SetArrayField(TEXT("component_scale"),Scale); B->SetArrayField(TEXT("position_cm"),Position);
        Bones.Add(MakeShared<FJsonValueObject>(B));
    }
    R->SetArrayField(TEXT("bones"),Bones); return Json(R);
}

FString UPMX4UEPmxSkirtTools::BuildExperiment(const FString& ManifestPath)
{
    using namespace PmxSkirt;
    FString Text;
    TSharedPtr<FJsonObject> M;
    if (!FFileHelper::LoadFileToString(Text,*ManifestPath) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),M)
        || (M->GetStringField(TEXT("schema"))!=TEXT("mmd2ue.pmx-skirt-experiment.v1") && M->GetStringField(TEXT("schema"))!=TEXT("mmd2ue.pmx-full-experiment.v1"))) return Fail(TEXT("invalid manifest"));
    auto* Mesh=LoadObject<USkeletalMesh>(nullptr,*M->GetStringField(TEXT("mesh")));
    const FString Dest=M->GetStringField(TEXT("asset"));
    if (!Mesh || !Dest.StartsWith(TEXT("/Game/")) || UEditorAssetLibrary::DoesAssetExist(Dest)) return Fail(TEXT("missing mesh or destination already exists"));
    const auto Pose=Rest(Mesh);
    const auto& Ref=Mesh->GetRefSkeleton();
    if (M->GetArrayField(TEXT("landmarks")).Num()<3) return Fail(TEXT("at least three landmarks required"));
    const FBasis Basis=Fit(M->GetArrayField(TEXT("landmarks")),Mesh,Pose);
    if (Basis.Error>0.05) return Fail(FString::Printf(TEXT("PMX landmark alignment error %.6fcm"),Basis.Error));
    const auto& Bodies=M->GetArrayField(TEXT("bodies"));
    const auto& Joints=M->GetArrayField(TEXT("joints"));
    TSet<FName> Names;
    for (const auto& V:Bodies)
    {
        const auto O=V->AsObject(); const FName N(*O->GetStringField(TEXT("target_bone")));
        const int32 I=Ref.FindBoneIndex(N);
        if (I<0 || !Pose[I].GetScale3D().Equals(FVector::OneVector,0.001)) return Fail(TEXT("missing or non-unit simulation bone: ")+N.ToString());
        Names.Add(N);
    }
    for (const auto& V:Joints)
    {
        const auto O=V->AsObject();
        if (!Names.Contains(FName(*O->GetStringField(TEXT("source_bone")))) || !Names.Contains(FName(*O->GetStringField(TEXT("target_bone"))))) return Fail(TEXT("joint endpoint missing"));
        if (!(Vec(O,TEXT("angular_min_rad"))+Vec(O,TEXT("angular_max_rad"))).IsNearlyZero(1e-5)) return Fail(TEXT("asymmetric angular PMX limits require explicit frame-offset conversion"));
    }
    auto* Asset=NewObject<UPhysicsAsset>(CreatePackage(*Dest),*FPackageName::GetShortName(Dest),RF_Public|RF_Standalone|RF_Transactional);
    TMap<FName,USkeletalBodySetup*> Setups;
    TMap<FName,double> Inertias;
    int32 Dynamic=0;
    for (const auto& V:Bodies)
    {
        const auto O=V->AsObject(); const FName N(*O->GetStringField(TEXT("target_bone")));
        auto*& Setup=Setups.FindOrAdd(N);
        if (!Setup)
        {
            Setup=NewObject<USkeletalBodySetup>(Asset,NAME_None,RF_Transactional);
            Setup->BoneName=N;
            Setup->PhysicsType=O->GetBoolField(TEXT("kinematic"))?PhysType_Kinematic:PhysType_Simulated;
            Setup->bConsiderForBounds=true;
            if (Setup->PhysicsType==PhysType_Simulated) ++Dynamic;
            Setup->DefaultInstance.SetMassOverride(O->GetNumberField(TEXT("mass")));
            Setup->DefaultInstance.LinearDamping=-FMath::Loge(FMath::Max(1e-5,1-O->GetNumberField(TEXT("linear_attenuation"))));
            Setup->DefaultInstance.AngularDamping=-FMath::Loge(FMath::Max(1e-5,1-O->GetNumberField(TEXT("angular_attenuation"))));
            auto* Material=NewObject<UPhysicalMaterial>(Asset);
            Material->Friction=O->GetNumberField(TEXT("friction"));
            Material->Restitution=O->GetNumberField(TEXT("restitution"));
            Setup->PhysMaterial=Material;
            Asset->SkeletalBodySetups.Add(Setup);
        }
        const FTransform Local=Basis.Frame(O).GetRelativeTransform(Pose[Ref.FindBoneIndex(N)]);
        const FVector Size=Vec(O,TEXT("size_blender_m"))*100.0;
        // Scalar inertia estimate for an explicitly calibrated damping ratio,
        // not a claimed conversion of Bullet's spring damping implementation.
        Inertias.Add(N,O->GetNumberField(TEXT("mass"))*(Size.X*Size.X+Size.Y*Size.Y+Size.Z*Size.Z)/3.0);
        const FString Shape=O->GetStringField(TEXT("shape"));
        bool PerShape=false; M->TryGetBoolField(TEXT("per_shape_filter"),PerShape);
        const FName FilterName=PerShape?FName(*FString::Printf(TEXT("PMX_%d_%d_%d"),O->GetIntegerField(TEXT("source_index")),O->GetIntegerField(TEXT("group")),O->GetIntegerField(TEXT("mask")))):NAME_None;
        if (Shape==TEXT("box"))
        {
            auto& E=Setup->AggGeom.BoxElems.AddDefaulted_GetRef();
            E.SetName(FilterName);
            E.Center=Local.GetLocation(); E.Rotation=Local.Rotator();
            E.X=2*Size.X; E.Y=2*Size.Z; E.Z=2*Size.Y;
        }
        else if (Shape==TEXT("capsule"))
        {
            auto& E=Setup->AggGeom.SphylElems.AddDefaulted_GetRef();
            E.SetName(FilterName);
            E.Center=Local.GetLocation(); E.Rotation=Local.Rotator(); E.Radius=Size.X; E.Length=Size.Y;
        }
        else
        {
            auto& E=Setup->AggGeom.SphereElems.AddDefaulted_GetRef(); E.Center=Local.GetLocation(); E.Radius=Size.X;
            E.SetName(FilterName);
        }
    }
    TSet<FString> Allowed;
    for (const auto& V:M->GetArrayField(TEXT("collision_pairs")))
    {
        const auto& P=V->AsArray(); Allowed.Add(Pair(FName(*P[0]->AsString()),FName(*P[1]->AsString())));
    }
    double MaxFrameGap=0;
    int32 RadialApproximations=0;
    for (const auto& V:Joints)
    {
        const auto O=V->AsObject();
        auto* T=NewObject<UPhysicsConstraintTemplate>(Asset,NAME_None,RF_Transactional);
        auto& C=T->DefaultInstance;
        C.JointName=FName(*FString::Printf(TEXT("PMX_%d_%s"),O->GetIntegerField(TEXT("source_index")),*O->GetStringField(TEXT("kind"))));
        C.ConstraintBone1=FName(*O->GetStringField(TEXT("target_bone")));
        C.ConstraintBone2=FName(*O->GetStringField(TEXT("source_bone")));
        const FTransform World=Basis.Frame(O);
        const FTransform F1=World.GetRelativeTransform(Pose[Ref.FindBoneIndex(C.ConstraintBone1)]);
        // PMX linear limits are relative to the source joint frame. Shift that
        // frame by the midpoint to express a non-zero locked displacement.
        FVector Mid=(Vec(O,TEXT("linear_min_m"))+Vec(O,TEXT("linear_max_m")))*50.0;
        Mid.X*=Basis.Hand();
        FTransform SourceWorld=World;
        SourceWorld.AddToTranslation(World.TransformVectorNoScale(Mid));
        const FTransform F2=SourceWorld.GetRelativeTransform(Pose[Ref.FindBoneIndex(C.ConstraintBone2)]);
        C.SetRefFrame(EConstraintFrame::Frame1,F1); C.SetRefFrame(EConstraintFrame::Frame2,F2);
        MaxFrameGap=FMath::Max(MaxFrameGap,((F1*Pose[Ref.FindBoneIndex(C.ConstraintBone1)]).GetLocation()-(F2*Pose[Ref.FindBoneIndex(C.ConstraintBone2)]).GetLocation()).Size());
        const FVector L=(Vec(O,TEXT("linear_max_m"))-Vec(O,TEXT("linear_min_m")))*50.0;
        C.SetLinearLimits(L.X<1e-6?LCM_Locked:LCM_Limited,L.Y<1e-6?LCM_Locked:LCM_Limited,L.Z<1e-6?LCM_Locked:LCM_Limited,L.GetMax());
        if (!L.IsNearlyZero()) ++RadialApproximations;
        const FVector A=Vec(O,TEXT("angular_max_rad"))*(180.0/PI);
        C.SetAngularTwistLimit(A.X<1e-5?ACM_Locked:ACM_Limited,A.X);
        C.SetAngularSwing1Limit(A.Z<1e-5?ACM_Locked:ACM_Limited,A.Z);
        C.SetAngularSwing2Limit(A.Y<1e-5?ACM_Locked:ACM_Limited,A.Y);
        const FVector K=Vec(O,TEXT("angular_spring"))*M->GetObjectField(TEXT("conversion"))->GetNumberField(TEXT("angular_spring_scale"));
        C.SetAngularDriveMode(EAngularDriveMode::TwistAndSwing);
        C.SetAngularDriveAccelerationMode(false);
        C.SetOrientationDriveTwistAndSwing(K.X>0,K.Y>0 || K.Z>0);
        C.ProfileInstance.AngularDrive.TwistDrive.Stiffness=K.X;
        C.ProfileInstance.AngularDrive.SwingDrive.Stiffness=(K.Y+K.Z)*0.5;
        double DampingRatio=0;
        M->GetObjectField(TEXT("conversion"))->TryGetNumberField(TEXT("joint_damping_ratio"),DampingRatio);
        double Inertia=Inertias[C.ConstraintBone1];
        if (Setups[C.ConstraintBone2]->PhysicsType==PhysType_Simulated)
            Inertia=1.0/(1.0/Inertia+1.0/Inertias[C.ConstraintBone2]);
        C.ProfileInstance.AngularDrive.TwistDrive.Damping=2*DampingRatio*FMath::Sqrt(K.X*Inertia);
        C.ProfileInstance.AngularDrive.SwingDrive.Damping=2*DampingRatio*FMath::Sqrt((K.Y+K.Z)*0.5*Inertia);
        C.SetAngularVelocityDriveTwistAndSwing(DampingRatio>0 && K.X>0,DampingRatio>0 && (K.Y>0 || K.Z>0));
        const FVector KL=Vec(O,TEXT("linear_spring"));
        C.SetLinearDriveAccelerationMode(false);
        C.SetLinearPositionDrive(KL.X>0,KL.Y>0,KL.Z>0);
        C.SetLinearDriveParams(KL,FVector::ZeroVector,FVector::ZeroVector);
        C.ProfileInstance.bDisableCollision=!Allowed.Contains(Pair(C.ConstraintBone1,C.ConstraintBone2));
        // Projection and parent dominance are invalid for this closed-loop lattice.
        C.ProfileInstance.bEnableProjection=false;
        C.ProfileInstance.bEnableShockPropagation=false;
        C.ProfileInstance.bParentDominates=false;
        // UE serializes/applies DefaultProfile, NOT the currently edited
        // ProfileInstance. Without this, saved assets silently lose the limits
        // and drives authored above and game worlds use default constraints.
        T->SetDefaultProfile(C);
        Asset->ConstraintSetup.Add(T);
    }
    Asset->UpdateBodySetupIndexMap(); Asset->UpdateBoundsBodiesArray();
    int32 EnabledPairs=0;
    for (int32 A=0; A<Asset->SkeletalBodySetups.Num(); ++A) for (int32 B=A+1; B<Asset->SkeletalBodySetups.Num(); ++B)
    {
        if (Allowed.Contains(Pair(Asset->SkeletalBodySetups[A]->BoneName,Asset->SkeletalBodySetups[B]->BoneName))) ++EnabledPairs;
        else Asset->DisableCollision(A,B);
    }
    Asset->SolverType=EPhysicsAssetSolverType::RBAN;
    Asset->SolverSettings.PositionIterations=16;
    Asset->SolverSettings.VelocityIterations=2;
    Asset->SolverSettings.ProjectionIterations=0;
    Asset->SolverSettings.FixedTimeStep=1.f/120.f;
    Asset->SolverSettings.bUseLinearJointSolver=false;
    const TSharedPtr<FJsonObject>* Solver=nullptr;
    if (M->TryGetObjectField(TEXT("solver"),Solver))
    {
        Asset->SolverSettings.PositionIterations=(*Solver)->GetIntegerField(TEXT("position_iterations"));
        Asset->SolverSettings.FixedTimeStep=(*Solver)->GetNumberField(TEXT("fixed_time_step"));
        Asset->SolverSettings.MaxDepenetrationVelocity=(*Solver)->GetNumberField(TEXT("max_depenetration_velocity"));
        bool Linear=false;
        if ((*Solver)->TryGetBoolField(TEXT("use_linear_joint_solver"),Linear)) Asset->SolverSettings.bUseLinearJointSolver=Linear;
    }
    Asset->SetPreviewMesh(Mesh);
    if (!Save(Asset)) return Fail(TEXT("cannot save Physics Asset"));
    auto R=MakeShared<FJsonObject>();
    R->SetStringField(TEXT("status"),TEXT("created_unassigned")); R->SetStringField(TEXT("asset"),Dest);
    R->SetNumberField(TEXT("dynamic_bodies"),Dynamic); R->SetNumberField(TEXT("kinematic_bodies"),Setups.Num()-Dynamic);
    R->SetNumberField(TEXT("joints"),Joints.Num()); R->SetNumberField(TEXT("collision_pairs"),EnabledPairs);
    R->SetNumberField(TEXT("alignment_rms_cm"),Basis.Error); R->SetNumberField(TEXT("max_joint_rest_frame_gap_cm"),MaxFrameGap);
    R->SetNumberField(TEXT("linear_box_to_radial_approximations"),RadialApproximations);
    R->SetStringField(TEXT("basis"),FString::Printf(TEXT("%d:%d,%d:%d,%d:%d"),Basis.P[0],Basis.S[0],Basis.P[1],Basis.S[1],Basis.P[2],Basis.S[2]));
    return Json(R);
}

FString UPMX4UEPmxSkirtTools::MakeInPlaceTestAnimation(const FString& SourcePath,const FString& Destination)
{
    using namespace PmxSkirt;
    auto* Source=LoadObject<UAnimSequence>(nullptr,*SourcePath);
    if (!Source || !Destination.StartsWith(TEXT("/Game/")) || UEditorAssetLibrary::DoesAssetExist(Destination)) return Fail(TEXT("invalid animation source/destination"));
    TArray<FTransform> Keys;
    Source->GetDataModel()->GetBoneTrackTransforms(TEXT("Center"),Keys);
    if (Keys.Num()<2) return Fail(TEXT("missing Center animation keys"));
    const FVector Delta=Keys.Last().GetLocation()-Keys[0].GetLocation();
    auto* Copy=DuplicateObject<UAnimSequence>(Source,CreatePackage(*Destination),*FPackageName::GetShortName(Destination));
    TArray<FVector3f> Positions,Scales; TArray<FQuat4f> Rotations;
    for (int32 I=0; I<Keys.Num(); ++I)
    {
        Positions.Add(FVector3f(Keys[I].GetLocation()-Delta*(double(I)/(Keys.Num()-1))));
        Rotations.Add(FQuat4f(Keys[I].GetRotation())); Scales.Add(FVector3f(Keys[I].GetScale3D()));
    }
    auto& Controller=Copy->GetController();
    Controller.OpenBracket(FText::FromString(TEXT("Isolated in-place physics test")),false);
    const bool Changed=Controller.SetBoneTrackKeys(TEXT("Center"),Positions,Rotations,Scales,false);
    Controller.CloseBracket(false);
    if (!Changed || !Save(Copy)) return Fail(TEXT("failed to save in-place test animation"));
    auto R=MakeShared<FJsonObject>(); R->SetStringField(TEXT("status"),TEXT("created_copy"));
    R->SetStringField(TEXT("source"),SourcePath); R->SetStringField(TEXT("asset"),Destination);
    R->SetStringField(TEXT("center_net_local_displacement_removed_cm"),Delta.ToString());
    return Json(R);
}

FString UPMX4UEPmxSkirtTools::BuildAnimBlueprint(const FString& MeshPath,const FString& PhysicsPath,const FString& AnimationPath,const FString& Destination,const FString& LeadingPhysicsPath)
{
    TArray<FString> Paths;
    if (!LeadingPhysicsPath.IsEmpty()) Paths.Add(LeadingPhysicsPath);
    Paths.Add(PhysicsPath);
    return BuildPhysicsBlueprint(MeshPath,Paths,AnimationPath,Destination);
}

FString UPMX4UEPmxSkirtTools::BuildPhysicsBlueprint(const FString& MeshPath,const TArray<FString>& PhysicsPaths,const FString& AnimationPath,const FString& Destination,bool bDeferred)
{
    using namespace PmxSkirt;
    auto* Mesh=LoadObject<USkeletalMesh>(nullptr,*MeshPath);
    auto* Animation=AnimationPath.IsEmpty()?nullptr:LoadObject<UAnimSequence>(nullptr,*AnimationPath);
    // An empty list is an explicit animation-only performance control.
    if (!Mesh || (!AnimationPath.IsEmpty() && (!Animation || Animation->GetSkeleton()!=Mesh->GetSkeleton()))) return Fail(TEXT("missing inputs or animation skeleton mismatch"));
    TArray<UPhysicsAsset*> Assets;
    TSet<FName> DynamicBones;
    for (const FString& Path:PhysicsPaths)
    {
        auto* Asset=LoadObject<UPhysicsAsset>(nullptr,*Path);
        if (!Asset) return Fail(TEXT("missing physics asset: ")+Path);
        for (const auto& S:Asset->SkeletalBodySetups)
            if (S->PhysicsType==PhysType_Simulated)
            {
                if (DynamicBones.Contains(S->BoneName)) return Fail(TEXT("multiple solvers simulate bone: ")+S->BoneName.ToString());
                DynamicBones.Add(S->BoneName);
            }
        Assets.Add(Asset);
    }
    if (!Destination.StartsWith(TEXT("/Game/")) || UEditorAssetLibrary::DoesAssetExist(Destination)) return Fail(TEXT("AnimBP destination exists or invalid"));
    auto* Factory=NewObject<UAnimBlueprintFactory>();
    Factory->ParentClass=UAnimInstance::StaticClass(); Factory->TargetSkeleton=Mesh->GetSkeleton(); Factory->PreviewSkeletalMesh=Mesh;
    auto* BP=Cast<UAnimBlueprint>(Factory->FactoryCreateNew(UAnimBlueprint::StaticClass(),CreatePackage(*Destination),FName(*FPackageName::GetShortName(Destination)),RF_Public|RF_Standalone|RF_Transactional,nullptr,GWarn));
    UEdGraph* Graph=nullptr;
    for (UEdGraph* G:BP->FunctionGraphs) if (G->GetSchema()->IsA<UAnimationGraphSchema>()) Graph=G;
    if (!Graph) return Fail(TEXT("missing AnimGraph"));
    auto* Root=FBlueprintEditorUtils::GetAnimGraphRoot(Graph);
    UEdGraphNode* Input=nullptr;
    if (Animation)
    {
        FGraphNodeCreator<UAnimGraphNode_SequencePlayer> Make(*Graph);
        auto* Player=Make.CreateNode(); Player->Node.SetSequence(Animation); Player->Node.SetLoopAnimation(true); Make.Finalize(); Input=Player;
    }
    else
    {
        FGraphNodeCreator<UAnimGraphNode_LocalRefPose> Make(*Graph); Input=Make.CreateNode(); Make.Finalize();
    }
    FGraphNodeCreator<UAnimGraphNode_LocalToComponentSpace> MakeL(*Graph); auto* L=MakeL.CreateNode(); MakeL.Finalize();
    TArray<UEdGraphNode*> Chain={Input,L};
    for (auto* Asset:Assets)
    {
    bool Filtered=false;
    for (const auto& S:Asset->SkeletalBodySetups)
    {
        auto IsPmx=[](const auto& Es) { for (const auto& E:Es) if(E.GetName().ToString().StartsWith(TEXT("PMX_"))) return true; return false; };
        Filtered |= IsPmx(S->AggGeom.SphereElems) || IsPmx(S->AggGeom.BoxElems) || IsPmx(S->AggGeom.SphylElems);
    }
    UEdGraphNode* Rigid=nullptr;
    FAnimNode_RigidBody* RigidNode=nullptr;
    if (Filtered)
    {
        FGraphNodeCreator<UAnimGraphNode_PmxFilteredRigidBody> MakeR(*Graph); auto* R=MakeR.CreateNode(); MakeR.Finalize(); Rigid=R; RigidNode=&R->Node;
        for (const auto& S:Asset->SkeletalBodySetups)
        {
            int32 Index=0;
            auto Add=[&](const auto& Elements)->bool
            {
                for (const auto& E:Elements)
                {
                    TArray<FString> Tokens; E.GetName().ToString().ParseIntoArray(Tokens,TEXT("_"));
                    if (Tokens.Num()!=4 || Tokens[0]!=TEXT("PMX")) return false;
                    FPmxShapeFilter Row; Row.Bone=S->BoneName; Row.ShapeIndex=Index++;
                    Row.Group=FCString::Atoi(*Tokens[2]); Row.Mask=FCString::Atoi(*Tokens[3]);
                    R->Node.ShapeFilters.Add(Row);
                }
                return true;
            };
            // ChaosInterface::CreateGeometry: spheres, boxes, capsules.
            if (!Add(S->AggGeom.SphereElems) || !Add(S->AggGeom.BoxElems) || !Add(S->AggGeom.SphylElems)) return Fail(TEXT("missing PMX shape filter metadata"));
        }
    }
    else
    {
        FGraphNodeCreator<UAnimGraphNode_RigidBody> MakeR(*Graph); auto* R=MakeR.CreateNode(); MakeR.Finalize(); Rigid=R; RigidNode=&R->Node;
    }
    RigidNode->OverridePhysicsAsset=Asset; RigidNode->bDefaultToSkeletalMeshPhysicsAsset=false;
    RigidNode->SimulationSpace=ESimulationSpace::ComponentSpace;
    RigidNode->SimSpaceSettings.WorldAlpha=1.f;
    RigidNode->bForceDisableCollisionBetweenConstraintBodies=false;
    RigidNode->bEnableWorldGeometry=false;
    RigidNode->bOverrideWorldGravity=true;
    RigidNode->OverrideWorldGravity=FVector(0,0,-980.f);
    RigidNode->bClampLinearTranslationLimitToRefPose=false;
    RigidNode->EvaluationResetTime=0.f;
    RigidNode->SimulationTiming=bDeferred?ESimulationTiming::Deferred:ESimulationTiming::Synchronous;
    Rigid->NodeComment=Asset->GetName()+TEXT(": only asset-defined collisions; disjoint simulated bones");
    Chain.Add(Rigid);
    }
    FGraphNodeCreator<UAnimGraphNode_ComponentToLocalSpace> MakeC(*Graph); auto* C=MakeC.CreateNode(); MakeC.Finalize();
    Chain.Append({C,Root});
    auto Pin=[](UEdGraphNode* N,EEdGraphPinDirection D)->UEdGraphPin* { for (auto* P:N->Pins) if (P->Direction==D && UAnimationGraphSchema::IsPosePin(P->PinType)) return P; return nullptr; };
    for (int32 I=0; I<Chain.Num(); ++I)
    {
        Chain[I]->NodePosX=-1000+I*250;
        if (I+1<Chain.Num() && !Graph->GetSchema()->TryCreateConnection(Pin(Chain[I],EGPD_Output),Pin(Chain[I+1],EGPD_Input))) return Fail(TEXT("AnimGraph connection failed"));
    }
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(BP); FKismetEditorUtilities::CompileBlueprint(BP);
    if (!BP->GeneratedClass || BP->Status==BS_Error || !Save(BP)) return Fail(TEXT("AnimBP compile/save failed"));
    auto Result=MakeShared<FJsonObject>(); Result->SetStringField(TEXT("status"),TEXT("created_unassigned")); Result->SetStringField(TEXT("asset"),Destination);
    return Json(Result);
}

FString UPMX4UEPmxSkirtTools::TestExperiment(const FString& MeshPath,const FString& BlueprintPath,float Seconds,float FramesPerSecond,bool bMoveComponent,bool bCaptureSkirtTrajectory,const FString& MeasurementAnchor)
{
    using namespace PmxSkirt;
    auto* Mesh=LoadObject<USkeletalMesh>(nullptr,*MeshPath);
    auto* BP=LoadObject<UAnimBlueprint>(nullptr,*BlueprintPath);
    if (!Mesh || !BP || !BP->GeneratedClass || Seconds<=0 || Seconds>60 || FramesPerSecond<15 || FramesPerSecond>240) return Fail(TEXT("invalid test inputs"));
    const int32 Pelvis=Mesh->GetRefSkeleton().FindBoneIndex(FName(*MeasurementAnchor));
    if (Pelvis<0) return Fail(TEXT("missing measurement anchor: ")+MeasurementAnchor);
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(true).CreateNavigation(false).CreateAISystem(false).ShouldSimulatePhysics(false).SetTransactional(false);
    auto* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    GEngine->CreateNewWorldContext(EWorldType::Game).SetCurrentWorld(World);
    auto* Actor=World->SpawnActor<ASkeletalMeshActor>();
    auto* Body=Actor->GetSkeletalMeshComponent();
    Body->SetSkeletalMesh(Mesh); Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Body->SetAnimationMode(EAnimationMode::AnimationBlueprint); Body->SetAnimInstanceClass(BP->GeneratedClass);
    Body->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    Body->bEnableUpdateRateOptimizations=false;
    // Commandlets do not run the editor viewport's skeletal tick. Drive pose
    // evaluation explicitly, once per frame, after advancing world time.
    Body->SetComponentTickEnabled(false);
    World->InitializeActorsForPlay(FURL());
    World->BeginPlay();
    // Consume root motion for in-place gait. Actual actor motion is applied separately below.
    if (Body->GetAnimInstance()) Body->GetAnimInstance()->SetRootMotionMode(ERootMotionMode::IgnoreRootMotion);
    const auto Pose=Rest(Mesh);
    TArray<int32> Indices;
    TSet<FName> SimulatedNames;
    if (auto* Instance=Body->GetAnimInstance())
        if (auto* Interface=IAnimClassInterface::GetFromClass(Instance->GetClass()))
            for (auto* Property:Interface->GetAnimNodeProperties())
                if (Property->Struct->IsChildOf(FAnimNode_RigidBody::StaticStruct()))
                {
                    auto* Node=Property->ContainerPtrToValuePtr<FAnimNode_RigidBody>(Instance);
                    if (Node->OverridePhysicsAsset)
                        for (const auto& S:Node->OverridePhysicsAsset->SkeletalBodySetups)
                            if (S->PhysicsType==PhysType_Simulated) SimulatedNames.Add(S->BoneName);
                }
    auto Family=[](const FString& N)->FString
    {
        for (const TCHAR* Prefix:{TEXT("JacketBelt"),TEXT("Jacket"),TEXT("Skirt"),TEXT("Hair"),TEXT("Tie"),TEXT("Shirt"),TEXT("Chest"),TEXT("Earring")})
            if (N.StartsWith(Prefix)) return Prefix;
        return TEXT("Other");
    };
    struct FStats { int32 Count=0; double MaxStep=0,LastStep=0,Edge=1,EdgeAfter2=1; };
    TMap<FString,FStats> Stats;
    for (int32 I=0; I<Mesh->GetRefSkeleton().GetNum(); ++I)
        if (SimulatedNames.Contains(Mesh->GetRefSkeleton().GetBoneName(I)))
        {
            Indices.Add(I);
            ++Stats.FindOrAdd(Family(Mesh->GetRefSkeleton().GetBoneName(I).ToString())).Count;
        }
    const float Dt=1.f/FramesPerSecond;
    TArray<FVector> Previous;
    double MaxDisplacement=0,MaxStep=0,MaxEdgeRatio=1,LastSecondMaxStep=0;
    double MaxStepAfter2=0,MaxEdgeAfter2=1;
    FString WorstEdge; float WorstEdgeTime=0;
    bool Finite=true,Aborted=false;
    int32 EvaluatedFrames=0;
    TArray<double> EvaluationMs;
    double EvaluationTotal=0;
    TArray<TSharedPtr<FJsonValue>> Samples;
    for (int32 Frame=0; Frame<FMath::RoundToInt(Seconds*FramesPerSecond); ++Frame)
    {
        const float Time=Frame*Dt;
        if (bMoveComponent)
        {
            const float Phase=FMath::Max(0.f,Time-2.f);
            Actor->SetActorLocationAndRotation(FVector(100.f*FMath::Sin(Phase),0,0),FRotator(0,45.f*FMath::Sin(Phase*0.8f),0));
        }
        ++GFrameCounter;
        World->Tick(LEVELTICK_All,Dt);
        const double EvaluationStart=FPlatformTime::Seconds();
        Body->TickAnimation(Dt,false);
        Body->RefreshBoneTransforms();
        // Synchronous RBAN: this includes animation/pose evaluation and physics,
        // but excludes world setup, warmup, measurements and JSON serialization.
        const double ElapsedMs=(FPlatformTime::Seconds()-EvaluationStart)*1000.0;
        if (Time>=2.f) { EvaluationMs.Add(ElapsedMs); EvaluationTotal+=ElapsedMs; }
        ++EvaluatedFrames;
        const auto& Current=Body->GetComponentSpaceTransforms();
        if (Current.Num()!=Pose.Num()) { Finite=false; break; }
        double Step=0,Displacement=0,EdgeRatio=1;
        TArray<FVector> Now;
        for (int32 I:Indices)
        {
            if (Current[I].ContainsNaN()) { Finite=false; break; }
            const FVector P=Current[Pelvis].InverseTransformPosition(Current[I].GetLocation());
            auto& Stat=Stats[Family(Mesh->GetRefSkeleton().GetBoneName(I).ToString())];
            Now.Add(P);
            Displacement=FMath::Max(Displacement,(P-Pose[Pelvis].InverseTransformPosition(Pose[I].GetLocation())).Size());
            if (Previous.Num()==Indices.Num())
            {
                const double BoneStep=(P-Previous[Now.Num()-1]).Size();
                Step=FMath::Max(Step,BoneStep); Stat.MaxStep=FMath::Max(Stat.MaxStep,BoneStep);
                if (Time>Seconds-1.f) Stat.LastStep=FMath::Max(Stat.LastStep,BoneStep);
            }
            const int32 Parent=Mesh->GetRefSkeleton().GetParentIndex(I);
            const double RestLength=Parent>=0?(Pose[I].GetLocation()-Pose[Parent].GetLocation()).Size():0.0;
            if (RestLength>0.1)
            {
                const double Ratio=(Current[I].GetLocation()-Current[Parent].GetLocation()).Size()/RestLength;
                Stat.Edge=FMath::Max(Stat.Edge,Ratio);
                if (Time>2.f) Stat.EdgeAfter2=FMath::Max(Stat.EdgeAfter2,Ratio);
                EdgeRatio=FMath::Max(EdgeRatio,Ratio);
                if (Ratio>MaxEdgeRatio) { MaxEdgeRatio=Ratio; WorstEdge=Mesh->GetRefSkeleton().GetBoneName(I).ToString(); WorstEdgeTime=Time; }
            }
        }
        Previous=MoveTemp(Now); MaxStep=FMath::Max(MaxStep,Step); MaxDisplacement=FMath::Max(MaxDisplacement,Displacement);
        if (Time>Seconds-1.f) LastSecondMaxStep=FMath::Max(LastSecondMaxStep,Step);
        if (Time>2.f) { MaxStepAfter2=FMath::Max(MaxStepAfter2,Step); MaxEdgeAfter2=FMath::Max(MaxEdgeAfter2,EdgeRatio); }
        if (bCaptureSkirtTrajectory || Frame%FMath::RoundToInt(FramesPerSecond)==0)
        {
            auto S=MakeShared<FJsonObject>(); S->SetNumberField(TEXT("time_s"),Time); S->SetNumberField(TEXT("max_displacement_cm"),Displacement); S->SetNumberField(TEXT("max_step_cm"),Step);
            S->SetNumberField(TEXT("max_edge_ratio"),EdgeRatio);
            TArray<TSharedPtr<FJsonValue>> SkirtPositions;
            for (int32 I:Indices)
                if (Mesh->GetRefSkeleton().GetBoneName(I).ToString().StartsWith(TEXT("Skirt_")))
                {
                    const FVector P=Current[Pelvis].InverseTransformPosition(Current[I].GetLocation());
                    for (int32 A=0; A<3; ++A) SkirtPositions.Add(MakeShared<FJsonValueNumber>(P[A]));
                }
            S->SetArrayField(TEXT("skirt_positions_cm"),SkirtPositions);
            Samples.Add(MakeShared<FJsonValueObject>(S));
        }
        if (!Finite || Displacement>200) { Aborted=true; break; }
    }
    int32 NativeActors=0,AppliedFilters=0,FilterErrors=0;
    TArray<TSharedPtr<FJsonValue>> RuntimeSettings;
    TArray<TSharedPtr<FJsonValue>> HipFilters;
    if (auto* Instance=Body->GetAnimInstance())
    {
        if (auto* Interface=IAnimClassInterface::GetFromClass(Instance->GetClass()))
            for (auto* Property:Interface->GetAnimNodeProperties())
                if (Property->Struct->IsChildOf(FAnimNode_RigidBody::StaticStruct()))
                {
                    auto* Node=Property->ContainerPtrToValuePtr<FAnimNode_RigidBody>(Instance);
                    if (auto* Simulation=Node->GetSimulation()) NativeActors+=Simulation->NumActors();
                    auto Setting=MakeShared<FJsonObject>();
                    Setting->SetStringField(TEXT("timing"),Node->SimulationTiming==ESimulationTiming::Deferred?TEXT("deferred"):Node->SimulationTiming==ESimulationTiming::Synchronous?TEXT("synchronous"):TEXT("default"));
                    if (const auto* PA=Node->OverridePhysicsAsset.Get())
                    {
                        Setting->SetStringField(TEXT("asset"),PA->GetPathName());
                        Setting->SetNumberField(TEXT("position_iterations"),PA->SolverSettings.PositionIterations);
                        Setting->SetNumberField(TEXT("fixed_time_step"),PA->SolverSettings.FixedTimeStep);
                        Setting->SetBoolField(TEXT("use_linear_joint_solver"),PA->SolverSettings.bUseLinearJointSolver);
                    }
                    RuntimeSettings.Add(MakeShared<FJsonValueObject>(Setting));
                    if (Property->Struct==FAnimNode_PmxFilteredRigidBody::StaticStruct())
                    {
                        auto* Filtered=Property->ContainerPtrToValuePtr<FAnimNode_PmxFilteredRigidBody>(Instance);
                        AppliedFilters+=Filtered->AppliedShapeFilters; FilterErrors+=Filtered->FilterErrors;
                        if (auto* Sim=Node->GetSimulation())
                            for (int32 A=0; A<Sim->NumActors(); ++A)
                            {
                                auto* ActorHandle=Sim->GetActorHandle(A);
                                if (ActorHandle->GetName()!=TEXT("LowerBody")) continue;
                                const auto& Shapes=ActorHandle->GetParticle()->ShapesArray();
                                for (const auto& Row:Filtered->ShapeFilters)
                                    if (Row.Bone==TEXT("LowerBody") && Shapes.IsValidIndex(Row.ShapeIndex))
                                    {
                                        const auto& F=Shapes[Row.ShapeIndex]->GetShapeFilterData();
                                        auto H=MakeShared<FJsonObject>(); H->SetNumberField(TEXT("shape_index"),Row.ShapeIndex);
                                        H->SetNumberField(TEXT("group"),F.GetCollisionChannelIndex()); H->SetNumberField(TEXT("mask"),F.GetBlockChannels());
                                        H->SetStringField(TEXT("bounds_size_cm"),Shapes[Row.ShapeIndex]->GetGeometry()->BoundingBox().Extents().ToString());
                                        HipFilters.Add(MakeShared<FJsonValueObject>(H));
                                    }
                            }
                    }
                }
    }
    Actor->Destroy(); GEngine->DestroyWorldContext(World); World->DestroyWorld(false);
    auto R=MakeShared<FJsonObject>(); R->SetStringField(TEXT("status"),!Finite?TEXT("nonfinite_or_missing_pose"):(Aborted?TEXT("aborted_unstable"):(MaxStep<1e-7?TEXT("simulation_not_advancing"):TEXT("measured"))));
    R->SetStringField(TEXT("measurement_anchor"),MeasurementAnchor);
    TArray<TSharedPtr<FJsonValue>> BoneNames;
    for (int32 I:Indices) BoneNames.Add(MakeShared<FJsonValueString>(Mesh->GetRefSkeleton().GetBoneName(I).ToString()));
    R->SetArrayField(TEXT("simulated_bone_names"),BoneNames);
    R->SetNumberField(TEXT("simulated_bones"),Indices.Num()); R->SetNumberField(TEXT("max_displacement_cm"),MaxDisplacement);
    R->SetNumberField(TEXT("applied_shape_filters"),AppliedFilters); R->SetNumberField(TEXT("shape_filter_errors"),FilterErrors);
    auto Groups=MakeShared<FJsonObject>();
    for (const auto& Entry:Stats)
    {
        auto G=MakeShared<FJsonObject>(); G->SetNumberField(TEXT("bodies"),Entry.Value.Count);
        G->SetNumberField(TEXT("max_step_cm"),Entry.Value.MaxStep); G->SetNumberField(TEXT("last_second_step_cm"),Entry.Value.LastStep);
        G->SetNumberField(TEXT("max_bone_edge_ratio"),Entry.Value.Edge); G->SetNumberField(TEXT("max_edge_after_2s"),Entry.Value.EdgeAfter2);
        Groups->SetObjectField(Entry.Key,G);
    }
    R->SetObjectField(TEXT("families"),Groups);
    R->SetArrayField(TEXT("runtime_hip_shape_filters"),HipFilters);
    R->SetNumberField(TEXT("max_step_cm"),MaxStep); R->SetNumberField(TEXT("last_second_max_step_cm"),LastSecondMaxStep);
    R->SetNumberField(TEXT("max_bone_edge_ratio"),MaxEdgeRatio); R->SetArrayField(TEXT("samples"),Samples);
    R->SetNumberField(TEXT("native_rigidbody_actors"),NativeActors);
    R->SetArrayField(TEXT("runtime_solver_settings"),RuntimeSettings);
    R->SetNumberField(TEXT("evaluated_frames"),EvaluatedFrames);
    EvaluationMs.Sort();
    auto Timing=MakeShared<FJsonObject>();
    Timing->SetStringField(TEXT("scope"),TEXT("TickAnimation + RefreshBoneTransforms, including prior deferred task waits if any; no rendering; excludes first 2 seconds; not total async physics CPU cost"));
    Timing->SetNumberField(TEXT("samples"),EvaluationMs.Num());
    if (!EvaluationMs.IsEmpty())
    {
        Timing->SetNumberField(TEXT("mean_ms"),EvaluationTotal/EvaluationMs.Num());
        auto Percentile=[&](double P) { return EvaluationMs[FMath::Clamp(FMath::CeilToInt(P*EvaluationMs.Num())-1,0,EvaluationMs.Num()-1)]; };
        Timing->SetNumberField(TEXT("p50_ms"),Percentile(.5));
        Timing->SetNumberField(TEXT("p95_ms"),Percentile(.95));
        Timing->SetNumberField(TEXT("p99_ms"),Percentile(.99));
        Timing->SetNumberField(TEXT("max_ms"),EvaluationMs.Last());
    }
    R->SetObjectField(TEXT("evaluation_timing"),Timing);
    R->SetStringField(TEXT("worst_edge_bone"),WorstEdge); R->SetNumberField(TEXT("worst_edge_time"),WorstEdgeTime);
    R->SetNumberField(TEXT("max_step_after_2s_cm"),MaxStepAfter2); R->SetNumberField(TEXT("max_edge_after_2s"),MaxEdgeAfter2);
    return Json(R);
}
