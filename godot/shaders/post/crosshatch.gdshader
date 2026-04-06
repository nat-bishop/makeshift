shader_type canvas_item;

uniform sampler2D screen_texture : hint_screen_texture, filter_linear;
uniform float density : hint_range(10.0, 80.0) = 40.0;
uniform float threshold_light : hint_range(0.0, 1.0) = 0.7;
uniform float threshold_mid : hint_range(0.0, 1.0) = 0.4;
uniform vec4 ink_color : source_color = vec4(0.1, 0.08, 0.05, 1.0);
uniform vec4 paper_color : source_color = vec4(0.95, 0.93, 0.88, 1.0);

void fragment() {
	vec4 tex = texture(screen_texture, SCREEN_UV);
	float lum = dot(tex.rgb, vec3(0.299, 0.587, 0.114));

	vec2 px = SCREEN_UV * density;
	float hatch1 = step(0.5, fract(px.x + px.y));       // diagonal /
	float hatch2 = step(0.5, fract(px.x - px.y));       // diagonal backslash
	float hatch3 = step(0.5, fract(px.x));               // vertical

	float hatching = 1.0;
	if (lum < threshold_light) hatching -= hatch1 * 0.3;
	if (lum < threshold_mid) hatching -= hatch2 * 0.3;
	if (lum < threshold_mid * 0.5) hatching -= hatch3 * 0.3;

	COLOR = vec4(mix(ink_color.rgb, paper_color.rgb, hatching), 1.0);
}
