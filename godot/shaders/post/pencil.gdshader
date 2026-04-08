shader_type canvas_item;

// Pencil sketch effect: edge detection + paper texture noise.
uniform float edge_strength : hint_range(0.0, 2.0) = 1.0;
uniform float noise_strength : hint_range(0.0, 0.5) = 0.15;
uniform float paper_brightness : hint_range(0.5, 1.0) = 0.92;
uniform vec4 pencil_color : source_color = vec4(0.15, 0.12, 0.1, 1.0);

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void fragment() {
	vec2 px = SCREEN_PIXEL_SIZE;
	vec4 col = texture(TEXTURE, UV);

	// Simple edge detection (luminance gradient)
	float c  = dot(col.rgb, vec3(0.299, 0.587, 0.114));
	float l  = dot(texture(TEXTURE, UV + vec2(-px.x, 0.0)).rgb, vec3(0.299, 0.587, 0.114));
	float r  = dot(texture(TEXTURE, UV + vec2( px.x, 0.0)).rgb, vec3(0.299, 0.587, 0.114));
	float t  = dot(texture(TEXTURE, UV + vec2(0.0, -px.y)).rgb, vec3(0.299, 0.587, 0.114));
	float b  = dot(texture(TEXTURE, UV + vec2(0.0,  px.y)).rgb, vec3(0.299, 0.587, 0.114));

	float edge = abs(l - r) + abs(t - b);
	edge = clamp(edge * edge_strength * 4.0, 0.0, 1.0);

	// Paper noise
	float noise = hash(floor(FRAGCOORD.xy)) * noise_strength;

	// Combine: paper base with pencil marks on edges and dark areas
	float darkness = 1.0 - c;
	float pencil = clamp(edge + darkness * 0.3 + noise, 0.0, 1.0);

	vec3 paper = vec3(paper_brightness);
	COLOR = vec4(mix(paper, pencil_color.rgb, pencil), 1.0);
}
