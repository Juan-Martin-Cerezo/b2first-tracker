# Taste
- Communicates in Spanish (rioplatense); expects the agent to respond in the same language/dialect. Confidence: 0.9
- Prefers the agent to fully understand the project (read docs and relevant code) and ask clarifying questions before making any changes ("no hagas cambios... hace preguntas para entenderlo mejor"). Confidence: 0.9
- Prioritizes getting the tool into daily use quickly ("fase de armado pero lo quiero usar lo antes posible"); favors pragmatic, minimal-risk changes that reach a usable state fast over long-term polish. Confidence: 0.7
- Explicitly requires non-destructive, additive changes: "que no elimines nada" — never remove/alter existing functionality when adding features; preserve everything that already works. Confidence: 0.9
- Wants progress data stored robustly and accessible from any device ("que pueda estudiar desde donde sea y haya un lugar donde se guarde todo el progreso de forma sólida") — values cross-device persistence over browser-local-only storage. Confidence: 0.8
- Did not write the code himself and defers technical decisions to the agent ("De los test no sé nada", "no lo programé yo", "no estoy enterado"); prefers the agent to pick sensible technical solutions and inform him at a high level rather than ask him to decide implementation details. Confidence: 0.7
