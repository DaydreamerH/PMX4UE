#pragma once
#include "AnimGraphNode_SkeletalControlBase.h"
#include "AnimNode_PmxFilteredRigidBody.h"
#include "AnimGraphNode_PmxFilteredRigidBody.generated.h"

UCLASS()
class PMX4UEEDITOR_API UAnimGraphNode_PmxFilteredRigidBody : public UAnimGraphNode_SkeletalControlBase
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, Category=Settings) FAnimNode_PmxFilteredRigidBody Node;
    virtual FText GetNodeTitle(ENodeTitleType::Type) const override { return FText::FromString(TEXT("RigidBody (PMX shape filters)")); }
    virtual FText GetTooltipText() const override { return FText::FromString(TEXT("Native UE RigidBody solver with PMX per-shape group masks. No custom solver.")); }
    virtual FString GetNodeCategory() const override { return TEXT("PMX4UE|Physics"); }
protected:
    virtual FText GetControllerDescription() const override { return GetNodeTitle(ENodeTitleType::FullTitle); }
    virtual const FAnimNode_SkeletalControlBase* GetNode() const override { return &Node; }
};
