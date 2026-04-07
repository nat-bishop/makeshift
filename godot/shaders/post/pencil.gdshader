shader_type canvas_item;

uniform sampler2D screen_texture : hint_screen_texture, filter_linear;
uniform float threshold1 : hint_range(0.0, 1.0) = 0.75;
uniform float threshold2 : hint_range(0.0, 1.0) = 0.50;
uniform float threshold3 : hint_range(0.0, 1.0) = 0.25;
uniform float threshold4 : hint_range(0.0, 1.0) = 0.05;
uniform vec4 pencil_color : source_color = vec4(0.15, 0.12, 0.08, 1.0);
uniform vec4 paper_bg : source_color = vec4(0.95, 0.93, 0.88, 1.0);
uniform float pattern_tiling : hint_range(1.0, 20.0) = 8.0;
uniform float grain_strength : hint_range(0.0, 0.5) = 0.08;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = hash(i);
	float b = hash(i + vec2(1.0, 0.0));
	float c = hash(i + vec2(0.0, 1.0));
	float d = hash(i + vec2(1.0, 1.0));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float get_intensity(vec3 color) {
	return 0.299 * color.r + 0.587 * color.g + 0.114 * color.b;
}

// Procedural pencil stroke pattern (no texture needed)
float pencil_stroke(vec2 uv, float angle) {
	float c = cos(angle);
	float s = sin(angle);
	vec2 rotated = vec2(uv.x * c - uv.y * s, uv.x * s + uv.y * c);
	float line = sin(rotated.x * pattern_tiling * 40.0) * 0.5 + 0.5;
	float jitter = noise(uv * pattern_tiling * 10.0) * 0.3;
	return clamp(line + jitter, 0.0, 1.0);
}

void fragment() {
	vec4 tex = texture(screen_texture, SCREEN_UV);
	float intensity = get_intensity(tex.rgb);

	// Layer pencil strokes based on darkness
	float stroke1 = pencil_stroke(SCREEN_UV, 0.785);         // 45 degrees
	float stroke2 = pencil_stroke(SCREEN_UV + 0.1, -0.785);  // -45 degrees
	float stroke3 = pencil_stroke(SCREEN_UV + 0.2, 0.0);     // horizontal
	float stroke4 = pencil_stroke(SCREEN_UV + 0.3, 1.571);   // vertical

	float pencil_value = 1.0;
	if (intensity < threshold1) pencil_value *= mix(1.0, stroke1, 0.5);
	if (intensity < threshold2) pencil_value *= mix(1.0, stroke2, 0.5);
	if (intensity < threshold3) pencil_value *= mix(1.0, stroke3, 0.5);
	if (intensity < threshold4) pencil_value *= mix(1.0, stroke4, 0.5);

	// Paper grain
	float grain = (noise(SCREEN_UV * 500.0) - 0.5) * grain_strength;

	vec3 result = mix(pencil_color.rgb, paper_bg.rgb, pencil_value) + grain;
	COLOR = vec4(result, 1.0);
}
