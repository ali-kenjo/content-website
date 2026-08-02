#version 330 core

out vec4 fragColor;

uniform float iTime;
uniform vec2 iResolution;

float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * iResolution.xy) / iResolution.y;
    vec3 col = vec3(0.0);

    const float LAYERS = 4.0;
    for (float layer = 0.0; layer < LAYERS; layer += 1.0) {
        float depth = fract(layer / LAYERS + iTime * 0.02);
        float scale = mix(24.0, 2.0, depth);
        vec2 gv = uv * scale;
        vec2 id = floor(gv);
        vec2 gf = fract(gv) - 0.5;

        float n = hash(id + layer * 17.0);
        float starSize = 0.015 + 0.05 * n;
        float d = length(gf);
        float twinkle = 0.5 + 0.5 * sin(iTime * (1.0 + n * 3.0) + n * 6.28318);
        float star = smoothstep(starSize, 0.0, d) * twinkle;
        float fade = 1.0 - depth;

        col += vec3(star * fade * (0.6 + 0.4 * n));
    }

    fragColor = vec4(col, 1.0);
}
