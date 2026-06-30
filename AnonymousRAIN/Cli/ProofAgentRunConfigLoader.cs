using System.Text.Json;
using Serilog;

namespace ProofAgent.Cli;

public class ProofAgentRunConfigLoader
{
    #region Fields

    private const int _DefaultCheckTimeoutSeconds = 60;

    private const int _DefaultSearchHitContextLines = 2;

    private const int _DefaultExtraErrorCount = 2;

    private const string _DefaultLlmBaseUrl = "https://api.deepseek.com/v1/chat/completions";

    private const string _DefaultChatModel = "deepseek-v4-flash";

    private const string _DefaultReasoningEffort = "max";

    private const string _DefaultThinking = "enabled";

    private const int _DefaultLlmHttpTimeoutSeconds = 600;

    private static readonly JsonSerializerOptions _JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        ReadCommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true
    };

    private readonly ILogger _Logger;

    #endregion Fields

    public ProofAgentRunConfigLoader(ILogger logger)
    {
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    public bool TryLoad(
        string configJson,
        string runDirectory,
        string llmApiKeyFromEnvironment,
        out AgentInput agentInput)
    {
        agentInput = _EmptyAgentInput();

        if (string.IsNullOrWhiteSpace(configJson))
        {
            _Logger.Error("proofagent.config.json is empty.");
            return false;
        }

        ProofAgentRunConfigDocument document;
        try
        {
            document = JsonSerializer.Deserialize<ProofAgentRunConfigDocument>(configJson, _JsonOptions)
                ?? new ProofAgentRunConfigDocument();
        }
        catch (JsonException ex)
        {
            _Logger.Error(ex, "Failed to parse proofagent.config.json: {Message}", ex.Message);
            return false;
        }

        if (!_TryValidateLlmApiKey(llmApiKeyFromEnvironment))
        {
            return false;
        }

        var llmApiKey = llmApiKeyFromEnvironment.Trim();

        if (!_TryResolveRequiredTrimmed(document.TargetCoqFile, "targetCoqFile", out var targetCoqFile))
        {
            return false;
        }

        if (!_TryResolveRequiredTrimmed(document.UserMessage, "userMessage", out var userMessage))
        {
            return false;
        }

        if (!_TryResolveRequiredTrimmed(document.CheckCommand, "checkCommand", out var checkCommand))
        {
            return false;
        }

        if (!_TryResolveRequiredTrimmed(document.ParseSentenceScript, "parseSentenceScript", out var parseSentenceScript))
        {
            return false;
        }

        if (!_TryResolveProjectRoot(runDirectory, document.ProjectRoot, out var projectRoot))
        {
            return false;
        }

        var checkTimeoutSeconds = document.CheckTimeoutSeconds ?? _DefaultCheckTimeoutSeconds;
        if (!_TryValidatePositiveInt(checkTimeoutSeconds, "checkTimeoutSeconds"))
        {
            return false;
        }

        var searchHitContextLines = document.SearchHitContextLines ?? _DefaultSearchHitContextLines;
        if (!_TryValidateNonNegativeInt(searchHitContextLines, "searchHitContextLines"))
        {
            return false;
        }

        var extraErrorCount = document.ExtraErrorCount ?? _DefaultExtraErrorCount;
        if (!_TryValidateNonNegativeInt(extraErrorCount, "extraErrorCount"))
        {
            return false;
        }

        var baseUrl = (document.BaseUrl ?? _DefaultLlmBaseUrl).Trim();
        if (!_TryValidateBaseUrl(baseUrl))
        {
            return false;
        }

        var chatModel = (document.Model ?? _DefaultChatModel).Trim();
        if (string.IsNullOrWhiteSpace(chatModel))
        {
            _Logger.Error("model must not be empty.");
            return false;
        }

        var reasoningEffortRaw = (document.ReasoningEffort ?? _DefaultReasoningEffort).Trim();
        if (!_TryValidateReasoningEffort(reasoningEffortRaw, out var reasoningEffort))
        {
            return false;
        }

        var thinkingRaw = (document.Thinking ?? _DefaultThinking).Trim();
        if (!_TryValidateThinking(thinkingRaw, out var thinking))
        {
            return false;
        }

        var llmHttpTimeoutSeconds = document.LlmHttpTimeoutSeconds ?? _DefaultLlmHttpTimeoutSeconds;
        if (!_TryValidatePositiveInt(llmHttpTimeoutSeconds, "llmHttpTimeoutSeconds"))
        {
            return false;
        }

        if (!_TryResolveExtraReadableRootPaths(document.ExtraReadableRootPaths, out var extraReadableRootPaths))
        {
            return false;
        }

        agentInput = new AgentInput(
            projectRoot,
            targetCoqFile,
            checkTimeoutSeconds,
            checkCommand,
            parseSentenceScript,
            searchHitContextLines,
            extraErrorCount,
            userMessage,
            llmApiKey,
            baseUrl,
            chatModel,
            reasoningEffort,
            thinking,
            llmHttpTimeoutSeconds,
            extraReadableRootPaths);
        return true;
    }

    #region Private Methods

    private static AgentInput _EmptyAgentInput()
    {
        return new AgentInput(
            "",
            "",
            _DefaultCheckTimeoutSeconds,
            "",
            "",
            _DefaultSearchHitContextLines,
            _DefaultExtraErrorCount,
            "",
            "",
            _DefaultLlmBaseUrl,
            _DefaultChatModel,
            _DefaultReasoningEffort,
            _DefaultThinking,
            _DefaultLlmHttpTimeoutSeconds,
            Array.Empty<string>());
    }

    private bool _TryResolveExtraReadableRootPaths(
        List<string>? pathsFromDocument,
        out IReadOnlyList<string> normalizedPaths)
    {
        normalizedPaths = Array.Empty<string>();
        if (pathsFromDocument == null || pathsFromDocument.Count == 0)
        {
            return true;
        }

        var resolved = new List<string>();
        for (var i = 0; i < pathsFromDocument.Count; i++)
        {
            var raw = pathsFromDocument[i]?.Trim() ?? "";
            if (raw.Length == 0)
            {
                _Logger.Error("extraReadableRootPaths[{Index}] must not be empty.", i);
                return false;
            }

            if (!Path.IsPathRooted(raw))
            {
                _Logger.Error(
                    "extraReadableRootPaths[{Index}] must be an absolute path; got: {Path}",
                    i,
                    pathsFromDocument[i]);
                return false;
            }

            var fullPath = Path.GetFullPath(raw);
            resolved.Add(fullPath);
        }

        normalizedPaths = resolved;
        return true;
    }

    private bool _TryValidateLlmApiKey(string llmApiKeyFromEnvironment)
    {
        if (string.IsNullOrWhiteSpace(llmApiKeyFromEnvironment))
        {
            _Logger.Error("LLM_API_KEY environment variable is required (non-empty after trim).");
            return false;
        }

        return true;
    }

    private bool _TryResolveRequiredTrimmed(string? value, string fieldName, out string trimmed)
    {
        trimmed = value?.Trim() ?? "";
        if (trimmed.Length == 0)
        {
            _Logger.Error("{FieldName} is required (non-empty after trim).", fieldName);
            return false;
        }

        return true;
    }

    private bool _TryResolveProjectRoot(string runDirectory, string? projectRootFromConfig, out string absoluteProjectRoot)
    {
        absoluteProjectRoot = "";
        if (string.IsNullOrWhiteSpace(runDirectory))
        {
            _Logger.Error("Run directory is required to resolve projectRoot.");
            return false;
        }

        var runDirFull = Path.GetFullPath(runDirectory);
        if (string.IsNullOrWhiteSpace(projectRootFromConfig))
        {
            absoluteProjectRoot = runDirFull;
            return true;
        }

        var trimmed = projectRootFromConfig.Trim();
        absoluteProjectRoot = Path.IsPathRooted(trimmed)
            ? Path.GetFullPath(trimmed)
            : Path.GetFullPath(Path.Combine(runDirFull, trimmed));
        return true;
    }

    private bool _TryValidatePositiveInt(int value, string fieldName)
    {
        if (value < 1)
        {
            _Logger.Error("{FieldName} must be a positive integer; got {Value}.", fieldName, value);
            return false;
        }

        return true;
    }

    private bool _TryValidateNonNegativeInt(int value, string fieldName)
    {
        if (value < 0)
        {
            _Logger.Error("{FieldName} must be a non-negative integer; got {Value}.", fieldName, value);
            return false;
        }

        return true;
    }

    private bool _TryValidateBaseUrl(string baseUrl)
    {
        if (baseUrl.Length == 0)
        {
            _Logger.Error("baseUrl must not be empty.");
            return false;
        }

        if (!Uri.TryCreate(baseUrl, UriKind.Absolute, out var uri) ||
            (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps))
        {
            _Logger.Error("baseUrl must be an absolute http or https URL; got: {BaseUrl}", baseUrl);
            return false;
        }

        return true;
    }

    private bool _TryValidateReasoningEffort(string raw, out string normalized)
    {
        normalized = raw.ToLowerInvariant();
        if (normalized is "high" or "max" or "low" or "medium" or "xhigh")
        {
            return true;
        }

        _Logger.Error(
            "reasoningEffort must be one of: high, max, low, medium, xhigh; got: {ReasoningEffort}",
            raw);
        normalized = "";
        return false;
    }

    private bool _TryValidateThinking(string raw, out string normalized)
    {
        normalized = raw.ToLowerInvariant();
        if (normalized is "enabled" or "disabled")
        {
            return true;
        }

        _Logger.Error("thinking must be one of: enabled, disabled; got: {Thinking}", raw);
        normalized = "";
        return false;
    }

    #endregion Private Methods
}
