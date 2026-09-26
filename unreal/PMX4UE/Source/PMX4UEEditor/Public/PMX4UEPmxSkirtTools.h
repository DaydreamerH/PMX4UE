#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "PMX4UEPmxSkirtTools.generated.h"

/** Isolated PMX lattice experiments on the unchanged UpperOnlyCm mesh. */
UCLASS()
class PMX4UEEDITOR_API UPMX4UEPmxSkirtTools : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Read-only target skeleton positions/scales for physics planning. */
    UFUNCTION(BlueprintCallable, Category="PMX4UE|Physics")
    static FString InspectPhysicsMesh(const FString& MeshPath);

    /** One native node per independent Physics Asset; no cross-node proxies added.
     * Deferred uses the engine task scheduler and previous-frame physics output.
     * Existing callers default to synchronous behavior. */
    UFUNCTION(BlueprintCallable, Category="PMX4UE|Physics")
    static FString BuildPhysicsBlueprint(const FString& MeshPath, const TArray<FString>& PhysicsPaths,
        const FString& AnimationPath, const FString& Destination, bool bDeferred = false);

    UFUNCTION(BlueprintCallable, Category="PMX4UE|Physics")
    static FString MakeInPlaceTestAnimation(const FString& SourcePath, const FString& Destination);

    UFUNCTION(BlueprintCallable, Category="PMX4UE|Physics")
    static FString BuildExperiment(const FString& ManifestPath);

    /** Empty AnimationPath makes a reference-pose experiment. Optional leading
     * native pass requires disjoint simulated bones; outer proxies are kinematic. */
    UFUNCTION(BlueprintCallable, Category="PMX4UE|Physics")
    static FString BuildAnimBlueprint(const FString& MeshPath, const FString& PhysicsPath,
        const FString& AnimationPath, const FString& Destination, const FString& LeadingPhysicsPath = TEXT(""));

    /** Transient world; optional every-frame skirt trajectory for isolation regression.
     * Samples actual native RigidBody output, never saves mesh/scene. */
    UFUNCTION(BlueprintCallable, Category="PMX4UE|Physics")
    static FString TestExperiment(const FString& MeshPath, const FString& BlueprintPath,
        float Seconds = 12.f, float FramesPerSecond = 60.f, bool bMoveComponent = false,
        bool bCaptureSkirtTrajectory = false, const FString& MeasurementAnchor = TEXT("LowerBody"));
};
