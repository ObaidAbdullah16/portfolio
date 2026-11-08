/* Bedrock Bill-Shock Calculator - the maths (no DOM here, so it is easy to test).
 *
 * Why bills surprise people: the pricing page shows "price per token", and the
 * first estimate multiplies it by "question + answer". Real applications send far
 * more tokens on every call: the system prompt, the whole chat history, retrieved
 * documents (RAG), tool results in agent loops, and retries. Guardrails, the
 * vector database and logging are billed on top. This file adds all of it up.
 *
 * Works in the browser (window.BedrockCalc) and in Node (module.exports) for tests.
 */
(function (root) {
  "use strict";

  var DEFAULTS = {
    model: "claude-haiku-4-5",
    endpoint: "global",          // "global" or "geo" (geographic / in-region: +10% on some models)
    users: 500,                  // daily active users
    conversationsPerUser: 2,     // conversations per user per day
    turns: 6,                    // user messages per conversation
    systemTokens: 1500,          // system prompt + tool definitions, sent on every call
    userTokens: 60,              // one user message
    outputTokens: 350,           // one final answer
    history: "full",             // "full" | "window" | "none"
    historyWindow: 4,            // turns kept when history = "window"
    ragChunks: 5,                // retrieved chunks added to every turn (0 = no RAG)
    chunkTokens: 300,
    agentSteps: 0,               // extra model calls per turn (tool use / agent loop)
    toolResultTokens: 400,       // tool output added to the context per step
    stepOutputTokens: 120,       // what the model writes when it calls a tool
    retryRate: 0.03,             // share of calls that are sent twice (timeouts, throttling, bad JSON)
    caching: false,              // cache the system prompt (where the model supports it)
    batchShare: 0,               // 0..1: share of the traffic sent through batch inference (-50%)
    guardrails: { contentFilters: false, deniedTopics: false, pii: false, grounding: false },
    guardrailScope: "user",      // "user" (user message + answer) or "full" (the whole prompt)
    vectorStore: "none",
    vectorStoreCustom: 0,        // USD/month for "custom" or "s3vectors"
    corpusTokens: 2000000,       // documents in the knowledge base, in tokens
    reindexPerMonth: 1,
    logging: false,              // model invocation logging to CloudWatch Logs
    priceOverrides: {}           // { modelId: { input, output } }
  };

  function num(v, fallback) {
    var n = Number(v);
    return Number.isFinite(n) && n >= 0 ? n : fallback;
  }

  function clone(o) { return JSON.parse(JSON.stringify(o)); }

  /* Merge user input over the defaults and clamp silly values. */
  function normalise(input) {
    var s = clone(DEFAULTS);
    input = input || {};
    Object.keys(s).forEach(function (k) {
      if (input[k] === undefined) return;
      if (typeof s[k] === "number") s[k] = num(input[k], s[k]);
      else if (typeof s[k] === "boolean") s[k] = Boolean(input[k]);
      else if (k === "guardrails") {
        Object.keys(s.guardrails).forEach(function (g) { s.guardrails[g] = Boolean((input.guardrails || {})[g]); });
      } else if (k === "priceOverrides") s[k] = input[k] || {};
      else s[k] = String(input[k]);
    });
    s.turns = Math.max(1, Math.round(s.turns));
    s.historyWindow = Math.max(0, Math.round(s.historyWindow));
    s.ragChunks = Math.round(s.ragChunks);
    s.agentSteps = Math.round(s.agentSteps);
    s.retryRate = Math.min(s.retryRate, 1);
    s.batchShare = Math.min(s.batchShare, 1);
    return s;
  }

  function findModel(prices, id) {
    for (var i = 0; i < prices.models.length; i++) if (prices.models[i].id === id) return prices.models[i];
    return prices.models[0];
  }

  /* Effective price per token for this setup (overrides, +10% geo endpoints). */
  function rates(s, prices) {
    var m = findModel(prices, s.model);
    var o = s.priceOverrides[m.id] || {};
    var geo = s.endpoint === "geo" && m.geoPremium ? 1 + prices.extras.geoPremium : 1;
    var input = num(o.input, m.input) * geo / 1e6;
    var output = num(o.output, m.output) * geo / 1e6;
    var canCache = s.caching && m.cacheRead !== null && s.systemTokens >= (m.cacheMin || 0);
    return {
      model: m,
      input: input,
      output: output,
      cacheRead: canCache ? input * m.cacheRead : input,
      cacheWrite: canCache ? input * m.cacheWrite : input,
      cached: canCache,
      batch: m.batch
    };
  }

  /* Guardrails bill each check in whole text units of up to 1,000 characters,
   * rounded up: a 240-character question is 1 unit, a 5,600-character prompt is 6. */
  function textUnits(tokens, charsPerToken) {
    return Math.ceil(tokens * charsPerToken / 1000);
  }

  /* Tokens of each kind for ONE conversation (before retries).
   * Each user turn = (agentSteps) tool-calling calls + 1 final call.
   * Every call re-sends: system prompt + history + RAG chunks + the user message
   * (+ the tool results gathered so far in this turn).
   * Also counts Guardrails text units for both scopes:
   *   guardUnitsUser: the user message and the final answer, checked once per turn;
   *   guardUnitsFull: everything sent and received, checked on every call. */
  function conversationTokens(s, charsPerToken) {
    var cpt = charsPerToken || 4;
    var t = { system: 0, history: 0, rag: 0, user: 0, tools: 0, output: 0, calls: 0, systemWrites: 0,
      guardUnitsUser: 0, guardUnitsFull: 0 };
    var rag = s.ragChunks * s.chunkTokens;
    var perTurnPair = s.userTokens + s.outputTokens;
    for (var k = 1; k <= s.turns; k++) {
      var past = k - 1;
      if (s.history === "none") past = 0;
      else if (s.history === "window") past = Math.min(past, s.historyWindow);
      var historyTokens = past * perTurnPair;
      var calls = s.agentSteps + 1;
      t.guardUnitsUser += textUnits(s.userTokens, cpt) + textUnits(s.outputTokens, cpt);
      for (var j = 0; j < calls; j++) {
        var toolsSoFar = j * (s.toolResultTokens + s.stepOutputTokens);  // earlier steps of this turn
        var out = j < calls - 1 ? s.stepOutputTokens : s.outputTokens;
        t.system += s.systemTokens;
        t.history += historyTokens;
        t.rag += rag;
        t.user += s.userTokens;
        t.tools += toolsSoFar;
        t.output += out;
        t.calls += 1;
        t.guardUnitsFull += textUnits(s.systemTokens + historyTokens + rag + s.userTokens + toolsSoFar, cpt) +
          textUnits(out, cpt);
      }
    }
    t.systemWrites = 1; // with caching, the prefix is written once per conversation (5-minute cache)
    return t;
  }

  /* The full monthly estimate. */
  function estimate(input, prices) {
    var s = normalise(input);
    var x = prices.extras;
    var r = rates(s, prices);
    var conv = conversationTokens(s, x.charsPerToken);
    var convPerMonth = s.users * s.conversationsPerUser * x.daysPerMonth;
    var retry = 1 + s.retryRate;

    // Batch inference halves token prices but cannot use the prompt cache.
    var batchShare = r.batch ? s.batchShare : 0;
    var onDemand = 1 - batchShare;
    var batchFactor = batchShare * x.batchDiscount;

    function tokenCost(tokens, price) { return tokens * price * (onDemand + batchFactor); }

    // System prompt: cached (read) on most calls when caching is on.
    var systemCost;
    if (r.cached) {
      var writes = conv.systemWrites * s.systemTokens;
      var reads = conv.system - writes;
      systemCost = onDemand * (writes * r.cacheWrite + reads * r.cacheRead) + batchFactor * conv.system * r.input;
    } else {
      systemCost = tokenCost(conv.system, r.input);
    }

    var perConv = {
      system: systemCost,
      history: tokenCost(conv.history, r.input),
      rag: tokenCost(conv.rag, r.input),
      user: tokenCost(conv.user, r.input),
      tools: tokenCost(conv.tools, r.input),
      output: tokenCost(conv.output, r.output)
    };
    var modelPerConv = 0;
    Object.keys(perConv).forEach(function (k) { modelPerConv += perConv[k]; });

    // Guardrails: each policy type is billed per 1,000 text units; every check rounds up
    // to whole units, separately for what goes in and what comes out.
    var g = s.guardrails, gp = x.guardrails;
    var perThousandUnits = (g.contentFilters ? gp.contentFilters : 0) + (g.deniedTopics ? gp.deniedTopics : 0) +
      (g.pii ? gp.pii : 0) + (g.grounding ? gp.grounding : 0);
    var units = s.guardrailScope === "full" ? conv.guardUnitsFull : conv.guardUnitsUser;
    var guardrailsPerConv = units * perThousandUnits / 1000;

    // Knowledge base: the vector store (fixed), embedding the corpus and each question.
    // "custom" uses the amount entered; S3 Vectors is usage-based, so it uses the amount
    // entered, or the listed starting estimate while that is still 0.
    var vs = x.vectorStores[s.vectorStore] || x.vectorStores.none;
    var vectorStoreMonthly = s.vectorStore === "custom" ? s.vectorStoreCustom
      : s.vectorStore === "s3vectors" ? (s.vectorStoreCustom > 0 ? s.vectorStoreCustom : vs.monthly)
        : vs.monthly;
    var ragOn = s.ragChunks > 0;
    var embedMonthly = ragOn
      ? (s.corpusTokens * s.reindexPerMonth + s.userTokens * s.turns * convPerMonth) * x.embeddingPerMTok / 1e6
      : 0;

    // Invocation logging: every prompt and answer stored in CloudWatch Logs (~1.3x JSON overhead).
    var allTokens = (conv.system + conv.history + conv.rag + conv.user + conv.tools + conv.output) * retry * convPerMonth;
    var logsMonthly = s.logging ? allTokens * x.charsPerToken * 1.3 / 1e9 * x.logsPerGB : 0;

    var breakdown = {
      system: perConv.system * retry * convPerMonth,
      history: perConv.history * retry * convPerMonth,
      rag: perConv.rag * retry * convPerMonth,
      user: perConv.user * retry * convPerMonth,
      tools: perConv.tools * retry * convPerMonth,
      output: perConv.output * retry * convPerMonth,
      guardrails: guardrailsPerConv * retry * convPerMonth,
      vectorStore: vectorStoreMonthly,
      embeddings: embedMonthly,
      logging: logsMonthly
    };
    var retriesCost = modelPerConv * s.retryRate * convPerMonth;
    var total = 0;
    Object.keys(breakdown).forEach(function (k) { total += breakdown[k]; });

    // The "pricing page" estimate most people start with: question + answer, nothing else.
    var naive = (s.userTokens * r.input + s.outputTokens * r.output) * s.turns * convPerMonth;

    var inputTokens = (conv.system + conv.history + conv.rag + conv.user + conv.tools) * retry;
    return {
      settings: s,
      model: r.model,
      cached: r.cached,
      monthly: total,
      daily: total / x.daysPerMonth,
      perConversation: convPerMonth ? total / convPerMonth : 0,
      perUserMonth: s.users ? total / s.users : 0,
      naiveMonthly: naive,
      multiplier: naive > 0 ? total / naive : 0,
      retriesCost: retriesCost,
      breakdown: breakdown,
      tokens: {
        inputPerConversation: Math.round(inputTokens),
        outputPerConversation: Math.round(conv.output * retry),
        callsPerConversation: conv.calls,
        conversationsPerMonth: convPerMonth,
        lastTurnInput: s.systemTokens + s.ragChunks * s.chunkTokens + s.userTokens +
          s.agentSteps * (s.toolResultTokens + s.stepOutputTokens) +
          (s.history === "none" ? 0 : Math.min(s.turns - 1, s.history === "window" ? s.historyWindow : s.turns) * (s.userTokens + s.outputTokens))
      }
    };
  }

  /* Ways to cut the bill, each as a changed copy of the settings, sorted by savings. */
  function savings(input, prices) {
    var s = normalise(input);
    var base = estimate(s, prices).monthly;
    var ideas = [];
    function tryIdea(id, title, why, change) {
      var next = clone(s);
      change(next);
      var m = estimate(next, prices).monthly;
      if (base - m > 0.005 && (base - m) / base >= 0.01) {
        ideas.push({ id: id, title: title, why: why, monthly: m, saves: base - m, savesPct: (base - m) / base, settings: next });
      }
    }
    var model = findModel(prices, s.model);
    if (s.history === "full" && s.turns > 5) {
      tryIdea("history", "Keep only the last 4 turns of chat history",
        "Every message re-sends the whole conversation. A sliding window (or a running summary) stops the growth.",
        function (n) { n.history = "window"; n.historyWindow = 4; });
    }
    if (!s.caching && model.cacheRead !== null && s.systemTokens >= (model.cacheMin || 0)) {
      tryIdea("caching", "Turn on prompt caching for the system prompt",
        "The same system prompt is sent on every call; cached reads cost a fraction of normal input.",
        function (n) { n.caching = true; });
    }
    if (s.ragChunks > 3) {
      tryIdea("rag", "Retrieve 3 chunks instead of " + s.ragChunks,
        "More context is not always better. Re-rank and keep the best 3; measure answer quality before and after.",
        function (n) { n.ragChunks = 3; });
    }
    if (s.outputTokens > 300) {
      tryIdea("maxtokens", "Cap answers at 300 tokens (max_tokens + a 'be concise' instruction)",
        "Output tokens cost several times more than input tokens.",
        function (n) { n.outputTokens = 300; });
    }
    if (s.agentSteps > 2) {
      tryIdea("agent", "Limit the agent to 2 tool calls per question",
        "Each step re-sends the full context. Give the agent better tools instead of more steps.",
        function (n) { n.agentSteps = 2; });
    }
    if (s.guardrailScope === "full" && anyGuardrail(s)) {
      tryIdea("guardscope", "Check only the user's message and the answer with Guardrails",
        "Tag the user input (guardContent) so system prompt and retrieved documents are not scanned on every call.",
        function (n) { n.guardrailScope = "user"; });
    }
    if (s.vectorStore === "opensearchClassic" || s.vectorStore === "opensearchDev") {
      tryIdea("vectors", "Move the knowledge base to S3 Vectors",
        "OpenSearch Serverless (classic) bills its minimum capacity 24/7, even with zero queries.",
        function (n) { n.vectorStore = "s3vectors"; n.vectorStoreCustom = 5; });
    }
    if (s.endpoint === "geo" && model.geoPremium) {
      tryIdea("global", "Use the Global cross-Region endpoint (if data residency allows)",
        "Geographic and in-Region endpoints cost 10% more for this model.",
        function (n) { n.endpoint = "global"; });
    }
    if (model.batch && s.batchShare < 0.3) {
      tryIdea("batch", "Send non-urgent work (summaries, tagging, reports) through batch inference",
        "Batch is 50% cheaper when an answer can wait up to a day. Shown here for 30% of the traffic.",
        function (n) { n.batchShare = 0.3; });
    }
    // A cheaper model: the next tier down (cheaper on both input and output),
    // preferring the same provider, where prompts usually transfer best.
    var cheaper = prices.models
      .filter(function (m) { return m.input < model.input && m.output < model.output; })
      .sort(function (a, b) { return (b.input + b.output) - (a.input + a.output); });
    var sameProvider = cheaper.filter(function (m) { return m.provider === model.provider; });
    var target = sameProvider[0] || cheaper[0];
    if (target) {
      tryIdea("model", "Try " + target.name + " (cheaper on input and output)",
        "Newer or smaller models handle many requests just as well. Route by difficulty, and test on your own examples before switching.",
        function (n) { n.model = target.id; });
    }
    ideas.sort(function (a, b) { return b.saves - a.saves; });
    return { base: base, ideas: ideas };
  }

  function anyGuardrail(s) {
    return s.guardrails.contentFilters || s.guardrails.deniedTopics || s.guardrails.pii || s.guardrails.grounding;
  }

  /* Shareable state: settings in the URL fragment (never sent to a server). */
  function encodeState(input) {
    var json = JSON.stringify(normalise(input));
    var b64 = typeof btoa === "function" ? btoa(unescape(encodeURIComponent(json))) : Buffer.from(json, "utf8").toString("base64");
    return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function decodeState(str) {
    try {
      var b64 = String(str).replace(/-/g, "+").replace(/_/g, "/");
      while (b64.length % 4) b64 += "=";
      var json = typeof atob === "function" ? decodeURIComponent(escape(atob(b64))) : Buffer.from(b64, "base64").toString("utf8");
      return normalise(JSON.parse(json));
    } catch (e) {
      return null;
    }
  }

  var PRESETS = {
    support: { label: "Support chatbot with RAG", values: { model: "claude-haiku-4-5", users: 500, conversationsPerUser: 2, turns: 6, systemTokens: 1500, userTokens: 60, outputTokens: 350, history: "full", ragChunks: 5, chunkTokens: 300, agentSteps: 0, retryRate: 0.03, caching: false, vectorStore: "opensearchClassic", guardrails: { contentFilters: true, deniedTopics: true, pii: true, grounding: false }, guardrailScope: "full", logging: true } },
    agent: { label: "Internal agent with tools", values: { model: "claude-sonnet-4-6", users: 80, conversationsPerUser: 4, turns: 5, systemTokens: 4000, userTokens: 80, outputTokens: 400, history: "full", ragChunks: 0, agentSteps: 4, toolResultTokens: 800, stepOutputTokens: 150, retryRate: 0.05, caching: false, vectorStore: "none", logging: true } },
    summarizer: { label: "Document summarizer", values: { model: "nova-lite", users: 50, conversationsPerUser: 20, turns: 1, systemTokens: 400, userTokens: 6000, outputTokens: 500, history: "none", ragChunks: 0, agentSteps: 0, retryRate: 0.02, caching: false, batchShare: 0, vectorStore: "none", logging: false } },
    mvp: { label: "Startup MVP chat", values: { model: "nova-micro", users: 200, conversationsPerUser: 1, turns: 8, systemTokens: 600, userTokens: 50, outputTokens: 250, history: "full", ragChunks: 0, agentSteps: 0, retryRate: 0.03, caching: false, vectorStore: "none", logging: false } }
  };

  var api = { DEFAULTS: DEFAULTS, PRESETS: PRESETS, normalise: normalise, estimate: estimate, savings: savings,
    conversationTokens: conversationTokens, encodeState: encodeState, decodeState: decodeState, findModel: findModel };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.BedrockCalc = api;
})(this);
