shader_type canvas_item;

uniform float amplitude : hint_range(0.0, 0.1) = 0.03;
uniform float frequency : hint_range(0.0, 20.0) = 8.0;
uniform float speed : hint_range(0.0, 10.0) = 3.0;

void fragment() {
	vec2 uv = UV;
	uv.x += sin(uv.y * frequency + TIME * speed) * amplitude;
	uv.y += cos(uv.x * frequency + TIME * speed * 0.7) * amplitude * 0.5;
	COLOR = texture(TEXTURE, uv);
}
