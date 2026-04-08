shader_type canvas_item;

// Sobel edge detection overlay.
uniform float thickness : hint_range(0.5, 4.0) = 1.0;
uniform float threshold : hint_range(0.0, 1.0) = 0.1;
uniform vec4 edge_color : source_color = vec4(0.0, 0.0, 0.0, 1.0);

void fragment() {
	vec2 px = SCREEN_PIXEL_SIZE * thickness;
	vec4 col = texture(TEXTURE, UV);

	// Sample 3x3 kernel (luminance)
	float tl = dot(texture(TEXTURE, UV + vec2(-px.x, -px.y)).rgb, vec3(0.299, 0.587, 0.114));
	float t  = dot(texture(TEXTURE, UV + vec2( 0.0,  -px.y)).rgb, vec3(0.299, 0.587, 0.114));
	float tr = dot(texture(TEXTURE, UV + vec2( px.x, -px.y)).rgb, vec3(0.299, 0.587, 0.114));
	float l  = dot(texture(TEXTURE, UV + vec2(-px.x,  0.0 )).rgb, vec3(0.299, 0.587, 0.114));
	float r  = dot(texture(TEXTURE, UV + vec2( px.x,  0.0 )).rgb, vec3(0.299, 0.587, 0.114));
	float bl = dot(texture(TEXTURE, UV + vec2(-px.x,  px.y)).rgb, vec3(0.299, 0.587, 0.114));
	float b  = dot(texture(TEXTURE, UV + vec2( 0.0,   px.y)).rgb, vec3(0.299, 0.587, 0.114));
	float br = dot(texture(TEXTURE, UV + vec2( px.x,  px.y)).rgb, vec3(0.299, 0.587, 0.114));

	float gx = -tl - 2.0*l - bl + tr + 2.0*r + br;
	float gy = -tl - 2.0*t - tr + bl + 2.0*b + br;
	float edge = sqrt(gx*gx + gy*gy);

	float mask = step(threshold, edge);
	COLOR = mix(col, edge_color, mask);
}
