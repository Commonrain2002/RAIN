namespace ProofAgent.Cli;

public class AgentInput
{
    public AgentInput(
        string projectRoot,
        string targetCoqFile,
        int checkTimeoutSeconds,
        string checkCommand,
        string parseSentenceScript,
        int searchHitContextLines,
        int extraErrorCount,
        string initialUserMessage,
        string llmApiKey,
        string llmBaseUrl,
        string chatModel,
        string reasoningEffort,
        string thinking,
        int llmHttpTimeoutSeconds,
        IReadOnlyList<string> extraReadableRootPaths)
    {
        ProjectRoot = projectRoot;
        TargetCoqFile = targetCoqFile;
        CheckTimeoutSeconds = checkTimeoutSeconds;
        CheckCommand = checkCommand;
        ParseSentenceScript = parseSentenceScript;
        SearchHitContextLines = searchHitContextLines;
        ExtraErrorCount = extraErrorCount;
        InitialUserMessage = initialUserMessage;
        LlmApiKey = llmApiKey;
        LlmBaseUrl = llmBaseUrl;
        ChatModel = chatModel;
        ReasoningEffort = reasoningEffort;
        Thinking = thinking;
        LlmHttpTimeoutSeconds = llmHttpTimeoutSeconds;
        ExtraReadableRootPaths = extraReadableRootPaths;
    }

    public string ProjectRoot { get; }

    public string TargetCoqFile { get; }

    public int CheckTimeoutSeconds { get; }

    /// <summary>Shell line run at project root for proof check (from <c>proofagent.config.json</c>).</summary>
    public string CheckCommand { get; }

    /// <summary>When non-empty after trim: shell prefix at project root; one quoted absolute <c>.v</c> path is appended.</summary>
    public string ParseSentenceScript { get; }

    /// <summary>search tool: lines of context above and below each hit.</summary>
    public int SearchHitContextLines { get; }

    /// <summary>run_check multi-error tool: maximum additional errors to collect after the first failing check.</summary>
    public int ExtraErrorCount { get; }

    /// <summary>First user message to the model (non-empty after trim).</summary>
    public string InitialUserMessage { get; }

    /// <summary>OpenAI-compatible API bearer token (from environment <c>LLM_API_KEY</c>).</summary>
    public string LlmApiKey { get; }

    /// <summary>Full OpenAI-compatible chat completions URL used as the HTTP POST target.</summary>
    public string LlmBaseUrl { get; }

    /// <summary>OpenAI-compatible chat model id.</summary>
    public string ChatModel { get; }

    /// <summary>DeepSeek-style <c>thinking.reasoning_effort</c>.</summary>
    public string ReasoningEffort { get; }

    /// <summary>DeepSeek-style <c>thinking.type</c>: <c>enabled</c> or <c>disabled</c>.</summary>
    public string Thinking { get; }

    /// <summary>OpenAI-compatible HTTP client timeout for each chat completion request (seconds).</summary>
    public int LlmHttpTimeoutSeconds { get; }

    /// <summary>Absolute directory roots; files under each root are recursively readable via search_external/read_external (from proofagent.config.json).</summary>
    public IReadOnlyList<string> ExtraReadableRootPaths { get; }
}
