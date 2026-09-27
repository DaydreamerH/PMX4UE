#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "PMX4UEWorkflowTools.generated.h"

/** Config-driven workflow bridge; contains no character names or source paths. */
UCLASS()
class PMX4UEEDITOR_API UPMX4UEWorkflowTools : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Own temporary PIE session with requested client size; no saved settings. */
    UFUNCTION(BlueprintCallable, Category="PMX4UE|Workflow")
    static bool BeginPreviewWindow(int32 Width, int32 Height);
    /** Set actual render viewport dimensions in an owned PIE session. */
    UFUNCTION(BlueprintCallable, Category="PMX4UE|Workflow")
    static bool SetPreviewResolution(int32 Width, int32 Height);
    /** Only call on newly generated workflow ABPs; does not change PA or mesh. */
    UFUNCTION(BlueprintCallable, Category="PMX4UE|Workflow")
    static FString ConfigurePhysicsBlueprint(const FString& BlueprintPath, const FString& SettingsJson);
    /** Synthetic step/hitch test; explicit measurement bones, no periodic reset. */
    UFUNCTION(BlueprintCallable, Category="PMX4UE|Workflow")
    static FString TestMotion(const FString& MeshPath, const FString& BlueprintPath,
        float Seconds, float FramesPerSecond, bool bHitches, bool bMoveComponent,
        const FString& MeasurementAnchor, const TArray<FString>& MeasurementBones);
};
