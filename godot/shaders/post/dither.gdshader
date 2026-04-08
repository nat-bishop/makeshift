shader_type canvas_item;

// Bayer 4x4 ordered dithering.
uniform float color_depth : hint_range(2.0, 32.0) = 8.0;
uniform float intensity : hint_range(0.0, 1.0) = 0.5;

const mat4 BAYER = mat4(
	vec4( 0.0,  8.0,  2.0, 10.0),
	vec4(12.0,  4.0, 14.0,  6.0),
	vec4( 3.0, 11.0,  1.0,  9.0),
	vec4(15.0,  7.0, 13.0,  5.0)
);

void fragment() {
	vec4 col = texture(TEXTURE, UV);
	vec2 pixel = floor(mod(FRAGCOORD.xy, 4.0));
	float threshold = BAYER[int(pixel.x)][int(pixel.y)] / 16.0 - 0.5;
	col.rgb += threshold * intensity / color_depth;
	col.rgb = floor(col.rgb * color_depth + 0.5) / color_depth;
	COLOR = col;
}
