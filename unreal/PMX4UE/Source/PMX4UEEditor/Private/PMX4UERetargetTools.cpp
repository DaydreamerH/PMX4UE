#include "PMX4UERetargetTools.h"
#include "Engine/SkeletalMesh.h"
#include "Retargeter/IKRetargeter.h"
#include "Retargeter/IKRetargetProcessor.h"
#include "RetargetEditor/IKRetargeterController.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

namespace
{
TArray<TSharedPtr<FJsonValue>> Numbers(std::initializer_list<double> Values)
{
    TArray<TSharedPtr<FJsonValue>> Out;
    for (double Value : Values) Out.Add(MakeShared<FJsonValueNumber>(Value));
    return Out;
}
void TransformFields(TSharedPtr<FJsonObject> Row, const FString& Prefix, const FTransform& T)
{
    const FVector P = T.GetTranslation(), S = T.GetScale3D();
    const FQuat Q = T.GetRotation();
    Row->SetArrayField(Prefix + TEXT("position"), Numbers({P.X, P.Y, P.Z}));
    Row->SetArrayField(Prefix + TEXT("rotation"), Numbers({Q.X, Q.Y, Q.Z, Q.W}));
    Row->SetArrayField(Prefix + TEXT("scale"), Numbers({S.X, S.Y, S.Z}));
}
}

FString UPMX4UERetargetTools::InspectRetargetPose(const FString& RetargeterPath, bool bSource)
{
    TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
    UIKRetargeter* Asset = LoadObject<UIKRetargeter>(nullptr, *RetargeterPath);
    const ERetargetSourceOrTarget Side = bSource ? ERetargetSourceOrTarget::Source : ERetargetSourceOrTarget::Target;
    USkeletalMesh* Mesh = Asset ? Asset->GetPreviewMesh(Side) : nullptr;
    if (!Mesh || !Asset->GetCurrentRetargetPose(Side))
    {
        Report->SetStringField(TEXT("error"), TEXT("Missing retargeter, preview mesh or current pose"));
    }
    else
    {
        UIKRetargeterController* Controller = UIKRetargeterController::GetController(Asset);
        FRetargetSkeleton Skeleton;
        Skeleton.Initialize(Mesh, Side, Asset, Controller->GetPelvisBone(Side), FRetargetPoseScaleWithPivot());
        const TArray<FTransform>& Local = Skeleton.RetargetPoses.GetLocalRetargetPose();
        const TArray<FTransform>& Global = Skeleton.RetargetPoses.GetGlobalRetargetPose();
        const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
        TArray<TSharedPtr<FJsonValue>> Bones;
        for (int32 I = 0; I < Ref.GetNum(); ++I)
        {
            TSharedRef<FJsonObject> Row = MakeShared<FJsonObject>();
            Row->SetStringField(TEXT("name"), Ref.GetBoneName(I).ToString());
            Row->SetNumberField(TEXT("parent"), Ref.GetParentIndex(I));
            TransformFields(Row, TEXT("ref_"), Ref.GetRefBonePose()[I]);
            TransformFields(Row, TEXT("local_"), Local[I]);
            TransformFields(Row, TEXT("global_"), Global[I]);
            const FQuat Q = Controller->GetRotationOffsetForRetargetPoseBone(Ref.GetBoneName(I), Side);
            Row->SetArrayField(TEXT("offset"), Numbers({Q.X, Q.Y, Q.Z, Q.W}));
            Bones.Add(MakeShared<FJsonValueObject>(Row));
        }
        Report->SetArrayField(TEXT("bones"), Bones);
        Report->SetStringField(TEXT("mesh"), Mesh->GetPathName());
        Report->SetStringField(TEXT("pose"), Controller->GetCurrentRetargetPoseName(Side).ToString());
        Report->SetStringField(TEXT("side"), bSource ? TEXT("source") : TEXT("target"));
        const FVector Root = Controller->GetRootOffsetInRetargetPose(Side);
        Report->SetArrayField(TEXT("root_offset"), Numbers({Root.X, Root.Y, Root.Z}));
        Report->SetStringField(TEXT("status"), TEXT("inspected"));
    }
    FString Output;
    FJsonSerializer::Serialize(Report, TJsonWriterFactory<>::Create(&Output));
    return Output;
}
