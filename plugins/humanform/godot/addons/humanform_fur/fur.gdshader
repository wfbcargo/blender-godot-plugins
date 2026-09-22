shader_type spatial;
render_mode cull_back, depth_draw_opaque, diffuse_burley, specular_schlick_ggx;

// humanform shell fur: one shell of the skin mesh, pushed out along the normal.
//
// The mesh, the skin and the skeleton are the body's own, so the GPU skins the shell exactly as it
// skins the skin and the fur can never swim: a shell is the same surface, displaced along its own
// (already skinned) normal in view of the coverage map. Nothing is simulated and nothing is stored
// between frames.
//
//   COLOR      the coverage map, as a vertex colour (glTF COLOR_0): R density, G length / length_max_m,
//              B and A the flow's (cos, sin) in the tangent frame. It is not a texture because hm08's UV
//              atlas overlaps itself, and a coverage map rasterised into it came back with furred hands.
//   fur_colour the fur's own colour, sRGB, the region's pattern already mixed in
//   strands    tiled: R the height up the fur (0..1) the strand at that texel reaches, 0 for bare skin;
//              G that strand's own tone, the same the whole way along it. The strands are gathered into
//              clumps, because fur reads as fur by its clumps - per-texel noise reads as dirt.
//
// A shell at height `shell_t` keeps the texels whose strand reaches over it, so every shell has a
// different outline and no two stack into a band. The base coat (shell_t = 0) is opaque: it is what
// stands in for the skin under fur dense enough that the skin is not drawn at all.

uniform sampler2D fur_colour : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D strands : filter_linear_mipmap, repeat_enable;

uniform float length_max_m = 0.02;      // metres the map's G channel is a fraction of
uniform float uv_scale = 1.0;           // UV repeats of the strand tile over the body's UV unit square
uniform float lay = 0.55;               // 0 the fur stands out, 1 it lies flat along the flow
uniform float min_density = 0.02;
// Every shell, the base coat included, stands this far off the skin. Without it the base coat is coplanar
// with the skin it sits on and the two z-fight: pale patches of bare shoulder showed through the pelt in
// Godot, only where the skin was still drawn. humanform's body-hair shell lifts itself the same way
// (brows.BODY_HAIR_LIFT_M), and a hair does grow out of the skin, not along it.
uniform float base_lift_m = 0.0004;
uniform float cover_density = 0.75;     // at and above this the skin is not drawn, so the base coat is solid
// A coat, not a speckle: the base coat has to sit close in tone to the strands over it, or every gap
// between strands reads as a dark fleck and the pelt reads at 2 m as dirt rather than as fur.
uniform float root_shade = 0.86;        // how dark the fur is at the root: the light does not reach in
uniform float rim = 0.12;               // the tips catch the light
uniform float strand_tone = 0.20;       // how far one strand's tone may sit from its neighbour's
uniform float roughness_v = 0.62;
uniform float specular_v = 0.30;

// per shell. Each shell gets its own ShaderMaterial (they share this shader and its textures, so the cost
// is one small uniform buffer each): `instance uniform` would be tidier, but a plain uniform is one less
// thing that can silently not arrive, and a silent one cost this round an afternoon.
uniform float shell_t = 0.0;            // 0 the base coat, 1 the tips
uniform float shell_fade = 1.0;         // 1 drawn, 0 gone: what a level of detail moves, never visibility

varying float v_t;
varying vec2 v_uv;
varying vec4 v_map;

void vertex() {
	v_t = shell_t;
	v_uv = UV;
	vec4 m = COLOR;
	v_map = m;
	float len_m = m.g * length_max_m * step(min_density, m.r);
	vec2 dir = normalize(vec2(m.b, m.a) * 2.0 - 1.0 + vec2(1e-6, 0.0));
	// out along the normal, then over along the flow: the lean grows as t^2, so the fur bends rather
	// than shearing, which is what makes a shell stack read as hair and not as a comb
	vec3 along = dir.x * TANGENT + dir.y * BINORMAL;
	VERTEX += NORMAL * (base_lift_m + len_m * shell_t) + along * (len_m * shell_t * shell_t * lay);
}

uniform int debug_mode = 0;   // 1 the density map, 2 the length, 3 the strand mask, 4 the dither

void fragment() {
	vec4 m = v_map;
	if (debug_mode > 0) {
		float d = m.r;
		if (debug_mode == 2) { d = m.g; }
		if (debug_mode == 3) { d = texture(strands, v_uv * uv_scale).r; }
		if (debug_mode == 4) { d = texture(strands, v_uv * uv_scale * 2.7 + vec2(0.37, 0.71)).r; }
		ALBEDO = vec3(0.0);
		ROUGHNESS = 1.0;
		SPECULAR = 0.0;
		EMISSION = vec3(d);
	} else {
	if (m.r < min_density) {
		discard;
	}
	vec2 st = texture(strands, v_uv * uv_scale).rg;
	float h = st.r;
	// How solid the fur is here: 1 where the skin under it is not drawn at all, falling to 0 at the edge
	// of the coverage map. A hard cut-off drew a stair of whole texels at every wrist and ankle, because
	// an alpha test cannot fade; so the edge is stochastic instead - the same strand texture read at
	// another scale as the threshold, which mips into a soft edge and carries the fur's own grain.
	float solid = smoothstep(min_density, cover_density, m.r);
	// read at a much finer scale than the strands, so the dither is under a pixel even at 0.6 m and mips
	// into a smooth fade instead of showing as speckle
	float n = texture(strands, v_uv * uv_scale * 2.7 + vec2(0.37, 0.71)).r;
	float a;
	if (v_t <= 0.001) {
		a = step(n, solid);                 // the base coat: what stands in for the skin the fur hides
	} else {
		// the strand reaches `h`; this shell sits at v_t. A soft edge over a fraction of a shell's
		// height so the tips are not cut square.
		a = smoothstep(v_t - 0.06, v_t + 0.02, h) * step(n, solid);
	}
	a *= shell_fade;
	if (a < 0.35) {
		discard;
	}
	vec3 c = texture(fur_colour, v_uv).rgb;
	// the tone belongs to the strand and holds along its whole length, so a clump lies together
	ALBEDO = c * mix(root_shade, 1.0 + rim, v_t) * mix(1.0 - strand_tone, 1.0 + strand_tone, st.g);
	ROUGHNESS = roughness_v;
	SPECULAR = specular_v;
	// the fur's own occlusion: dark at the root, open at the tips
	AO = mix(0.86, 1.0, v_t);
	AO_LIGHT_AFFECT = 1.0;
	}
}
