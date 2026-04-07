shader_type canvas_item;

uniform sampler2D screen_texture : hint_screen_texture, filter_linear;
uniform float edge_threshold : hint_range(0.0, 1.0) = 0.15;
uniform vec4 line_color : source_color = vec4(0.15, 0.1, 0.05, 1.0);
uniform bool show_fill = true;

void fragment() {
	vec2 ps = SCREEN_PIXEL_SIZE;
	vec4 center = texture(screen_texture, SCREEN_UV);

	// Sobel luminance samples
	float tl = dot(texture(screen_texture, SCREEN_UV + vec2(-ps.x, -ps.y)).rgb, vec3(0.299, 0.587, 0.114));
	float t  = dot(texture(screen_texture, SCREEN_UV + vec2(0.0, -ps.y)).rgb, vec3(0.299, 0.587, 0.114));
	float tr = dot(texture(screen_texture, SCREEN_UV + vec2(ps.x, -ps.y)).rgb, vec3(0.299, 0.587, 0.114));
	float l  = dot(texture(screen_texture, SCREEN_UV + vec2(-ps.x, 0.0)).rgb, vec3(0.299, 0.587, 0.114));
	float r  = dot(texture(screen_texture, SCREEN_UV + vec2(ps.x, 0.0)).rgb, vec3(0.299, 0.587, 0.114));
	float bl = dot(texture(screen_texture, SCREEN_UV + vec2(-ps.x, ps.y)).rgb, vec3(0.299, 0.587, 0.114));
	float b  = dot(texture(screen_texture, SCREEN_UV + vec2(0.0, ps.y)).rgb, vec3(0.299, 0.587, 0.114));
	float br = dot(texture(screen_texture, SCREEN_UV + vec2(ps.x, ps.y)).rgb, vec3(0.299, 0.587, 0.114));

	float edge_h = -tl - 2.0 * l - bl + tr + 2.0 * r + br;
	float edge_v = -tl - 2.0 * t - tr + bl + 2.0 * b + br;
	float edge = length(vec2(edge_h, edge_v));

	if (edge > edge_threshold) {
		COLOR = line_color;
	} else if (show_fill) {
		COLOR = center;
	} else {
		COLOR = vec4(0.95, 0.93, 0.88, 1.0);
	}
}
