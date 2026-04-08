shader_type canvas_item;

// Quantize colors to a limited palette (posterization).
uniform int levels : hint_range(2, 32) = 8;

void fragment() {
	vec4 col = texture(TEXTURE, UV);
	float n = float(levels);
	col.rgb = floor(col.rgb * n + 0.5) / n;
	COLOR = col;
}
