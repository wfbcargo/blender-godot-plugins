# Plausible material values

Sources: Lagarde "Feeding a physically based shading model", DONTNOD PBR chart,
Filament material docs, physicallybased.info, Unreal "Physically Based
Materials". Godot `albedo_color` is sRGB-encoded (what the inspector shows);
Blender socket colours are linear. Convert: sRGB = 1.055·L^(1/2.4) − 0.055.

## Base colour of non-metals

Plausible band: **30-240 sRGB** (Filament tolerant), 50-240 strict.

| Material | Linear | sRGB 8-bit |
|---|---|---|
| Charcoal | 0.02-0.04 | 39-56 |
| Fresh asphalt | 0.04 | 56 |
| Worn asphalt | 0.12 | ~97 |
| Bare soil | 0.17 | ~115 |
| Green grass | 0.10-0.25 (disputed) | 90-137 |
| Brick | 0.26 | ~140 |
| Desert sand | 0.40-0.44 | ~170 |
| New concrete | 0.51-0.55 | 190-196 |
| White paint | 0.6-0.8 | 205-230 |
| Fresh snow | 0.80-0.90 | 231-243 |
| 18% grey card | 0.18 | 118 |

## Metals (base colour = specular colour, metallic 1)

| Metal | sRGB (Filament) |
|---|---|
| Silver | 0.97, 0.96, 0.91 |
| Aluminium | 0.91, 0.92, 0.92 |
| Gold | 1.00, 0.85, 0.57 |
| Copper | 0.97, 0.74, 0.62 |
| Brass | 0.98, 0.90, 0.59 |
| Platinum | 0.83, 0.81, 0.78 |
| Iron | 0.77, 0.78, 0.78 |
| Titanium | 0.76, 0.73, 0.69 |
| Chromium (linear, Lagarde) | 0.55, 0.56, 0.55 |

Metals sit at **≥ 170 sRGB**. A dark metal is a rough or dirty one, not a dark
base colour.

## Dielectric specular (F0)

F0 = ((n−1)/(n+1))². Almost everything is ~4%. In Godot that's
`metallic_specular` 0.5 (F0 = 0.16·s²), which you should leave alone except:

| Material | F0 | Godot metallic_specular |
|---|---|---|
| Water | 2% | ~0.35 |
| Skin | 2.8% | ~0.42 |
| Plastic, glass, most things | 4% | 0.5 |
| Ruby | 7.7% | ~0.69 |
| Diamond | 17% | ~1.0 |

Blender's IOR input is ignored by Godot's glTF import; set `metallic_specular`.

## Roughness (perceptual, as Godot and Blender use it)

| Surface | Roughness |
|---|---|
| Chrome, mirror, polished metal | 0.02-0.15 |
| Car clearcoat, varnish, wet surfaces, glossy plastic | 0.05-0.3 |
| Brushed metal, satin paint | 0.3-0.5 |
| Skin | 0.35-0.55 |
| Raw wood, leather | 0.5-0.8 |
| Concrete, stone, asphalt, soil | 0.75-0.95 |
| Cloth, matte | 0.8-1.0 |

Real surfaces are never uniform: ±0.05-0.15 variation from wear, dust and
smudges, correlated with cavities and edges. Uniform roughness on a large
surface is the "plastic" look.

## The common mistakes (all checked by the linters or capture)

1. Albedo too bright: > 240 sRGB, pure white paint.
2. Albedo too dark: < 30 sRGB. It also starves GI of bounce.
3. Lighting baked into albedo: AO, shadows or highlights in the diffuse texture.
   Look at the `unshaded` view: it should read as paint, with no light direction.
4. Metallic between 0.1 and 0.9 without a mask.
5. Dark metals (base colour < 170 sRGB).
6. Wrong colour space: albedo/emission must be sRGB; roughness, metallic,
   normal, AO, masks must be Non-Color (Blender) / imported as data (Godot).
7. Uniform roughness on big surfaces.
8. Oversaturated albedo: natural materials rarely exceed ~0.6 saturation.
9. Wrong scale: a 3 m door, 20 cm bricks. Scale drives GI, falloff and fog.
10. Unshaded materials in a lit scene.

## Godot material notes

- Untextured terrain or rock: `uv1_triplanar` (+ `uv1_world_triplanar`) avoids
  UV work and seams.
- Detail maps (`detail_enabled`) break up large surfaces cheaply.
- Skin and wax: `subsurf_scatter_enabled`; foliage and cloth: `backlight_*`.
- Clearcoat, anisotropy, refraction exist on StandardMaterial3D, but glTF
  import won't set them. Add them on the Godot side after import.
