/* Amazon Bedrock price data used by the calculator.
 *
 * USD per 1 million tokens, on-demand "Standard" tier, US East (N. Virginia),
 * Global cross-Region rate where a model offers one. Prices change often and
 * differ by region: every number here can be overridden in the page, and you
 * should check https://aws.amazon.com/bedrock/pricing/ before quoting a client.
 *
 * cacheRead / cacheWrite: multiples of the input price (null = no caching modeled).
 * cacheMin: smallest prompt prefix (tokens) the model will cache.
 * geoPremium: Geographic / in-Region endpoints cost 10% more than Global.
 * assumed: true marks a value we could not confirm in a public source.
 */
var BEDROCK_PRICES = {
  checked: "2026-10-26",
  basis: "US East (N. Virginia), on-demand Standard tier, Global cross-Region rate where offered",
  sources: [
    { name: "AWS Bedrock pricing page", url: "https://aws.amazon.com/bedrock/pricing/" },
    { name: "AWS docs: prompt caching", url: "https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html" },
    { name: "CloudForecast Bedrock pricing (19 Oct 2026)", url: "https://www.cloudforecast.io/blog/aws-bedrock-pricing/" },
    { name: "Calcaas Bedrock price list (12 Oct 2026)", url: "https://calcaas.com/llm-pricing/aws-bedrock" },
    { name: "CloudZero: why Bedrock bills exceed estimates", url: "https://www.cloudzero.com/blog/amazon-bedrock-pricing/" }
  ],
  models: [
    { id: "nova-micro", name: "Amazon Nova Micro", provider: "Amazon", input: 0.035, output: 0.14, cacheRead: 0.25, cacheWrite: 1, cacheMin: 1024, batch: true, geoPremium: false, assumed: true, note: "Text only. Cache-read rate assumed (Nova caching is supported; check the pricing page)." },
    { id: "nova-lite", name: "Amazon Nova Lite", provider: "Amazon", input: 0.06, output: 0.24, cacheRead: 0.25, cacheWrite: 1, cacheMin: 1024, batch: true, geoPremium: false, assumed: true, note: "Cache-read rate assumed." },
    { id: "nova-2-lite", name: "Amazon Nova 2 Lite", provider: "Amazon", input: 0.30, output: 2.50, cacheRead: 0.25, cacheWrite: 1, cacheMin: 1024, batch: true, geoPremium: true, assumed: true, note: "Reasoning tokens are billed as output. Cache-read rate assumed." },
    { id: "nova-pro", name: "Amazon Nova Pro", provider: "Amazon", input: 0.80, output: 3.20, cacheRead: 0.25, cacheWrite: 1, cacheMin: 1024, batch: true, geoPremium: false, assumed: true, note: "Cache-read rate assumed." },
    { id: "claude-haiku-5-5", name: "Claude Haiku 5.5", provider: "Anthropic", input: 0.10, output: 0.50, cacheRead: 0.10, cacheWrite: 1.25, cacheMin: 512, batch: false, geoPremium: true, note: "Prompts over 100K tokens are billed at $0.50 / $2.50." },
    { id: "claude-haiku-4-5", name: "Claude Haiku 4.5", provider: "Anthropic", input: 1.00, output: 5.00, cacheRead: 0.10, cacheWrite: 1.25, cacheMin: 4096, batch: true, geoPremium: true, note: "Caching needs a prefix of at least 4,096 tokens." },
    { id: "claude-sonnet-5-5", name: "Claude Sonnet 5.5", provider: "Anthropic", input: 2.00, output: 10.00, cacheRead: 0.05, cacheWrite: 1.25, cacheMin: 512, batch: false, geoPremium: true, note: "Cache reads at 5% of input." },
    { id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6", provider: "Anthropic", input: 3.00, output: 15.00, cacheRead: 0.10, cacheWrite: 1.25, cacheMin: 1024, batch: true, geoPremium: true, note: "" },
    { id: "claude-opus-5-5", name: "Claude Opus 5.5", provider: "Anthropic", input: 4.00, output: 20.00, cacheRead: 0.05, cacheWrite: 1.25, cacheMin: 512, batch: false, geoPremium: true, note: "Cache reads at 5% of input." },
    { id: "llama-4-scout", name: "Llama 4 Scout 17B", provider: "Meta", input: 0.17, output: 0.66, cacheRead: null, cacheWrite: null, cacheMin: null, batch: true, geoPremium: false, note: "" },
    { id: "llama-4-maverick", name: "Llama 4 Maverick 17B", provider: "Meta", input: 0.24, output: 0.97, cacheRead: null, cacheWrite: null, cacheMin: null, batch: true, geoPremium: false, note: "" },
    { id: "mistral-large-3", name: "Mistral Large 3", provider: "Mistral AI", input: 0.50, output: 1.50, cacheRead: null, cacheWrite: null, cacheMin: null, batch: false, geoPremium: false, note: "" },
    { id: "gpt-oss-120b", name: "gpt-oss-120b", provider: "OpenAI (open weights)", input: 0.15, output: 0.60, cacheRead: null, cacheWrite: null, cacheMin: null, batch: true, geoPremium: false, note: "" }
  ],
  extras: {
    // Guardrails: USD per 1,000 text units (1 text unit = up to 1,000 characters)
    guardrails: { contentFilters: 0.15, deniedTopics: 0.15, pii: 0.10, grounding: 0.10 },
    // Embeddings: USD per 1M tokens (Titan Text Embeddings V2)
    embeddingPerMTok: 0.02,
    // Vector stores: USD per month for the store itself
    vectorStores: {
      none: { name: "No knowledge base", monthly: 0 },
      opensearchClassic: { name: "OpenSearch Serverless (classic, 2 OCU minimum)", monthly: 350.40 },
      opensearchDev: { name: "OpenSearch Serverless dev/test (redundancy off, about half)", monthly: 175.20 },
      s3vectors: { name: "S3 Vectors (usage-based; enter your estimate)", monthly: 5 },
      custom: { name: "Other / custom amount", monthly: 0 }
    },
    // CloudWatch Logs ingestion for model invocation logging, USD per GB
    logsPerGB: 0.50,
    charsPerToken: 4,
    batchDiscount: 0.5,
    geoPremium: 0.10,
    daysPerMonth: 30
  }
};

if (typeof module !== "undefined") { module.exports = BEDROCK_PRICES; }
