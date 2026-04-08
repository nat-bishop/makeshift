shader_type canvas_item;

// Crosshatch shading based on luminance.
uniform float density : hint_range(2.0, 20.0) = 10.0;
uniform float line_width : hint_range(0.5, 3.0) = 1.0;
uniform vec4 ink_color : source_color = vec4(0.1, 0.08, 0.05, 1.0);
uniform vec4 paper_color : source_color = vec4(0.95, 0.92, 0.88, 1.0);

void fragment() {
	vec4 col = texture(TEXTURE, UV);
	float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

	vec2 px = FRAGCOORD.xy;
	float s = density;

	// Diagonal hatch layers — more layers for darker areas
	float h1 = step(line_width, mod(px.x + px.y, s));       // brightest hatch
	float h2 = step(line_width, mod(px.x - px.y, s));       // medium dark
	float h3 = step(line_width, mod(px.x + px.y + s*0.5, s)); // darker
	float h4 = step(line_width, mod(px.x - px.y + s*0.5, s)); // darkest

	float hatch = 1.0;
	if (lum < 0.8) hatch = min(hatch, h1);
	if (lum < 0.55) hatch = min(hatch, h2);
	if (lum < 0.35) hatch = min(hatch, h3);
	if (lum < 0.15) hatch = min(hatch, h4);

	COLOR = mix(ink_color, paper_color, hatch);
}
