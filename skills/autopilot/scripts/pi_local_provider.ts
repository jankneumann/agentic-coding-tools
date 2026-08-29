/** Register the operator-configured OpenAI-compatible endpoint for one Pi run. */
export default function localProviderExtension(pi: any) {
  const baseUrl = process.env.LOCAL_INFERENCE_BASE_URL;
  const model = process.env.LOCAL_INFERENCE_MODEL;
  const configuredKey = process.env.LOCAL_INFERENCE_API_KEY;

  if (!baseUrl || !model) {
    throw new Error("LOCAL_INFERENCE_BASE_URL and LOCAL_INFERENCE_MODEL are required");
  }

  pi.registerProvider("local", {
    baseUrl,
    apiKey: configuredKey || "local-no-auth",
    authHeader: Boolean(configuredKey),
    api: "openai-completions",
    compat: {
      supportsDeveloperRole: false,
      supportsReasoningEffort: false,
    },
    models: [
      {
        id: model,
        name: model,
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 131072,
        maxTokens: 32768,
      },
    ],
  });
}
