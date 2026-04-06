shader_type canvas_item;

uniform int num_colors : hint_range(2, 16) = 8;
uniform sampler2D PALETTE_TEXTURE : hint_default_black;
uniform sampler2D screen_texture : hint_screen_texture, filter_linear;

vec3 palette_limiter(in vec3 albedo) {
	vec3 closest_color;
	float min_dist = 2.0;
	float n = float(num_colors);
	for (int i = 0; i < num_colors; i++) {
		float index = 1.0 / (2.0 * n) + float(i) / n;
		vec3 index_color = texture(PALETTE_TEXTURE, vec2(index, 0.5)).rgb;
		float dist = length(index_color - albedo);
		if (dist < min_dist) {
			min_dist = dist;
			closest_color = index_color;
			if (min_dist < 0.001) {
				return closest_color;
			}
		}
	}
	return closest_color;
}

void fragment() {
	vec4 tex = texture(screen_texture, SCREEN_UV);
	COLOR.rgb = palette_limiter(tex.rgb);
	COLOR.a = tex.a;
}
