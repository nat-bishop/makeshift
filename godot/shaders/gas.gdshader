shader_type canvas_item;

uniform float drift_speed : hint_range(0.0, 2.0) = 0.5;
uniform float alpha_pulse : hint_range(0.0, 0.5) = 0.2;

void fragment() {
	vec2 uv = UV;
	uv.y -= TIME * drift_speed * 0.02;
	uv.x += sin(TIME * 1.5 + UV.y * 4.0) * 0.015;
	vec4 col = texture(TEXTURE, uv);
	col.a *= 0.8 + alpha_pulse * sin(TIME * 2.0 + UV.x * 3.0);
	COLOR = col;
}
