"""Portable math/shader recipes distilled from a separately reviewed experiment.

No Unreal, model-specific coordinates, slots, or automatic visual approval.
All directions are WORLD-space, positions/distances use Unreal centimeters.
"""
import math
import re


def validate_band(config):
    if not isinstance(config, dict):
        raise ValueError('band must be an object')
    if config.get('reviewed') is not True or not str(config.get('review_evidence', '')).strip():
        raise ValueError('Review actual hair coverage, UV, mask and band fit first')
    if not re.fullmatch(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+', str(config.get('mask', ''))):
        raise ValueError('band mask must be an actual /Game texture package')
    if type(config.get('uv_channel')) is not int or config['uv_channel'] < 0:
        raise ValueError('Provide the reviewed mask uv_channel')
    for key in ('height_cm', 'width_cm', 'view_shift_cm', 'spec_normal_blend'):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(key + ' must be finite')
    if config['width_cm'] <= 0 or not 0 <= config['spec_normal_blend'] <= 1:
        raise ValueError('Positive band width and spec_normal_blend in [0,1] required')
    return dict(config)


def band_envelope(height, view_up, center_height, width, view_shift):
    """Height is relative to the calibrated sphere center, NOT the bone pivot."""
    if width <= 0:
        raise ValueError('width must be positive')
    q = (height - (center_height - view_up * view_shift)) / width
    return math.exp(-2 * q * q)


def interpolate_field(fields, yaw):
    """Five linear fields for -90,-45,0,45,90 deg; positive inside, edge=.5."""
    if len(fields) != 5 or not all(math.isfinite(x) for x in (*fields, yaw)):
        raise ValueError('Five finite distance fields and finite yaw required')
    q = (min(90, max(-90, yaw)) + 90) / 45
    i = min(3, int(q))
    return fields[i] * (1 - (q - i)) + fields[i + 1] * (q - i)


def eye_aperture(channels, side, positive_side_uses_r=True):
    """Do not union/min across eyes sharing UV. Sign comes from calibrated Left."""
    return channels[0 if (side >= 0) == positive_side_uses_r else 1]


def eye_composite(iris, white, hair, weight, white_is_behind_iris):
    """Reference scalar compositing: suppress hidden white before the iris pass."""
    background = hair if white_is_behind_iris else weight * white + (1 - weight) * hair
    return weight * iris + (1 - weight) * background


def source_coverage(alpha, alpha_scale, source_clip, masked):
    """Preserve original Masked coverage when making a translucent eye copy.

    Clip and scale are actual source material inputs, not reference defaults.
    Continuous source transparency uses clamped continuous coverage instead.
    """
    if type(masked) is not bool or any(isinstance(x, bool) or not isinstance(x, (int, float))
                                      or not math.isfinite(x) for x in (alpha, alpha_scale, source_clip)):
        raise ValueError('Finite source alpha/scale/clip and explicit masked flag required')
    if not 0 <= source_clip <= 1 or alpha_scale < 0:
        raise ValueError('Source clip must be in [0,1] and scale nonnegative')
    value = alpha * alpha_scale
    return float(value >= source_clip) if masked else min(1.0, max(0.0, value))


BAND_INPUTS = ('P', 'N', 'V', 'L', 'Center', 'Up', 'Mask', 'Height', 'Width',
               'ViewShift', 'NormalBlend', 'Power', 'MinIntensity')
BAND_HLSL = r'''
float3 up = Up / max(length(Up), 1e-6);
float3 v = V / max(length(V), 1e-6);
float3 l = L / max(length(L), 1e-6);
float3 hv = l + v;
if (dot(hv,hv) < 1e-8) return float3(0,0,0);
float3 sphere = P - Center;
sphere /= max(length(sphere), 1e-6);
float3 ns = lerp(N, sphere, saturate(NormalBlend));
ns /= max(length(ns), 1e-6);
float height = dot(P-Center, up);
float q = (height - (Height - dot(v,up)*ViewShift)) / max(Width,1e-4);
float band = exp(-2.0*q*q);
float lobe = saturate(MinIntensity + pow(saturate(dot(ns,normalize(hv))),max(Power,1.0)));
return band*lobe*saturate(Mask);
'''

# Separate angular fringe distance fields, NOT the face angular-threshold SDF.
# A.r/g/b/a = -90/-45/0/+45, B.r = +90, B.a = receiver coverage.
FRINGE_INPUTS = ('A', 'B', 'L', 'Forward', 'Left', 'Up', 'Receiver', 'Strength', 'Valid')
FRINGE_HLSL = r'''
float3 l = L/max(length(L),1e-6);
float f = dot(l,normalize(Forward));
float yaw = clamp(degrees(atan2(dot(l,normalize(Left)),f)),-90.0,90.0);
float q = (yaw+90.0)/45.0;
float field = q<1 ? lerp(A.r,A.g,q) : q<2 ? lerp(A.g,A.b,q-1) :
              q<3 ? lerp(A.b,A.a,q-2) : lerp(A.a,B.r,q-3);
float aa = max(fwidth(field)*0.7,1.0/255.0);
float contour = smoothstep(0.5-aa,0.5+aa,field);
return contour*saturate(B.a)*saturate(Receiver)*Strength*saturate(Valid)*
       smoothstep(0.0,0.15,f)*smoothstep(0.0,0.15,dot(l,normalize(Up)));
'''

PEEK_INPUTS = ('P', 'Head', 'Left', 'Forward', 'V', 'Aperture', 'PositiveSideUsesR',
               'Pixel', 'CD', 'SD', 'Stencil', 'StencilID', 'MinGap', 'MaxGap',
               'GapFade', 'SceneTolerance', 'SceneFade', 'FrontStart', 'FrontEnd',
               'Alpha', 'AlphaScale', 'SourceClip', 'CoverageMode', 'Strength', 'Valid')
PEEK_HLSL = r'''
float side = dot(P-Head,normalize(Left));
float useR = (side>=0.0)==(PositiveSideUsesR>=0.5) ? 1.0 : 0.0;
float aperture = lerp(Aperture.g,Aperture.r,useR);
float gap = Pixel-CD;
float stencil = 1.0-step(0.5,abs(Stencil-StencilID));
float front = smoothstep(FrontStart,max(FrontEnd,FrontStart+1e-4),
                        dot(normalize(V),normalize(Forward)));
float behind = step(MinGap,gap)*(1.0-smoothstep(MaxGap,MaxGap+max(GapFade,1e-4),gap));
float foreground = 1.0-smoothstep(SceneTolerance,SceneTolerance+max(SceneFade,1e-4),abs(SD-CD));
// Source Masked -> translucent copy retains its original binary coverage.
// CoverageMode is explicit: 1=Masked source, 0=continuous source transparency.
float sourceAlpha = Alpha*AlphaScale;
float coverage = CoverageMode>=0.5 ? step(SourceClip,sourceAlpha) : saturate(sourceAlpha);
return saturate(coverage*aperture*Strength*stencil*front*behind*foreground*Valid);
'''
