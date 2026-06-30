using System.Text.Json;
using ProofAgent.Llm;
using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Session;

public class LlmSession : ILlmSession
{
    #region Fields

    private readonly int _MaxToolRounds;

    private readonly ILlmProvider _Provider;

    private readonly ToolRegistry _ToolRegistry;

    private readonly IToolExecutionContext _ToolExecution;

    private readonly IContextCompressor _Compressor;

    private readonly List<LlmMessage> _History;

    private readonly ILogger _Logger;

    private LlmUsage _CumulativeLlmUsage;

    private readonly Action<LlmSessionUsageReport>? _OnReceiveHttpResponse;

    #endregion Fields

    #region Properties

    public IReadOnlyList<LlmMessage> History => _History;

    #endregion Properties

    public LlmSession(
        ILlmProvider provider,
        ToolRegistry toolRegistry,
        IToolExecutionContext toolExecution,
        IContextCompressor compressor,
        string initialSystemMessage,
        ILogger logger,
        int maxToolRounds,
        Action<LlmSessionUsageReport>? onEachHttpResponse = null)
    {
        if (maxToolRounds <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxToolRounds), "maxToolRounds must be a positive integer.");
        }

        _MaxToolRounds = maxToolRounds;
        _Provider = provider;
        _ToolRegistry = toolRegistry;
        _ToolExecution = toolExecution;
        _Compressor = compressor;
        _History = [];
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _OnReceiveHttpResponse = onEachHttpResponse;
        
        if (!string.IsNullOrEmpty(initialSystemMessage))
        {
            _History.Add(LlmMessage.CreateSystem(initialSystemMessage));
        }
    }

    public async Task<LlmChat> ChatAsync(string userMessage, LlmChatOptions chatOptions, CancellationToken cancellationToken)
    {
        userMessage ??= "";
        _Logger.Information(
            "LLM send: enableReasoning={EnableReasoning} reasoningEffort={ReasoningEffort} messageLength={MessageLength} historyCount={HistoryCount} message=\n{Message}",
            chatOptions.EnableReasoning,
            chatOptions.ReasoningEffort,
            userMessage.Length,
            _History.Count,
            userMessage);

        _History.Add(LlmMessage.CreateUser(userMessage));
        var rounds = 0;
        var chatUsage = LlmUsage.Zero;
        while (rounds < _MaxToolRounds)
        {
            rounds++;
            var step = await _ProcessOneToolRoundAsync(rounds, chatOptions, chatUsage, cancellationToken).ConfigureAwait(false);
            chatUsage = step.ChatUsage;
            if (step.CompletedResult != null)
            {
                return step.CompletedResult;
            }
        }

        _Logger.Warning(
            "LLM chat stopped: exceeded maximum tool rounds {MaxToolRounds}",
            _MaxToolRounds);
        return new LlmChat(_GetLastAssistantTextFromHistory(), chatUsage, exceededMaxToolRounds: true);
    }

    #region Private Methods

    private async Task<ToolRoundStep> _ProcessOneToolRoundAsync(
        int round,
        LlmChatOptions chatOptions,
        LlmUsage previousChatUsage,
        CancellationToken cancellationToken)
    {
        var response = await _RequestChatCompletionAsync(chatOptions, cancellationToken).ConfigureAwait(false);
        var newChatUsage = previousChatUsage.Add(response.Usage);

        _CumulativeLlmUsage = _CumulativeLlmUsage.Add(response.Usage);
        _LogReceivedChatCompletion(chatOptions, round, response);
        _NotifyHttpResponseUsage(chatOptions, round, response.Usage);
        _LogReasoningIfPresent(response);

        if (!_CheckContainsToolCalls(response))
        {
            return new ToolRoundStep
            {
                ChatUsage = newChatUsage,
                CompletedResult = _FinishWithAssistantTextOnly(response, newChatUsage)
            };
        }

        await _AppendAssistantToolCallsToHistoryAsync(response, cancellationToken).ConfigureAwait(false);
        return new ToolRoundStep
        {
            ChatUsage = newChatUsage,
            CompletedResult = null
        };
    }

    private async Task<LlmResponse> _RequestChatCompletionAsync(
        LlmChatOptions chatOptions,
        CancellationToken cancellationToken)
    {
        _CompressHistory();
        var declarations = _ToolRegistry.GetDeclarations();
        return await _Provider.ChatAsync(_History, declarations, chatOptions, cancellationToken).ConfigureAwait(false);
    }

    private void _CompressHistory()
    {
        var compressed = _Compressor.Compress(_History);
        var compressedCopy = compressed.ToList();
        _History.Clear();
        _History.AddRange(compressedCopy);
    }

    private void _LogReceivedChatCompletion(LlmChatOptions chatOptions, int round, LlmResponse response)
    {
        _Logger.Information(
            "LLM recv: enableReasoning={EnableReasoning} reasoningEffort={ReasoningEffort} round={Round}/{MaxRounds} textLength={TextLength} toolCalls={ToolCalls}",
            chatOptions.EnableReasoning,
            chatOptions.ReasoningEffort,
            round,
            _MaxToolRounds,
            response.Text.Length,
            response.ToolCalls.Count);
    }

    private void _LogReasoningIfPresent(LlmResponse response)
    {
        if (!string.IsNullOrWhiteSpace(response.ReasoningSummaryText))
        {
            _Logger.Information(
                "LLM reasoning summary: length={Length} text=\n{ReasoningSummaryText}",
                response.ReasoningSummaryText.Length,
                response.ReasoningSummaryText);
        }

        if (string.IsNullOrWhiteSpace(response.ReasoningText))
        {
            return;
        }

        if (!string.IsNullOrWhiteSpace(response.ReasoningSummaryText) &&
            string.Equals(response.ReasoningText.Trim(), response.ReasoningSummaryText.Trim(), StringComparison.Ordinal))
        {
            return;
        }

        _Logger.Information(
            "LLM thinking: length={Length} text=\n{ReasoningText}",
            response.ReasoningText.Length,
            response.ReasoningText);
    }

    private async Task _AppendAssistantToolCallsToHistoryAsync(
        LlmResponse response,
        CancellationToken cancellationToken)
    {
        _History.Add(LlmMessage.CreateAssistant(
            response.Text,
            response.ToolCalls,
            response.ReasoningText ?? ""));
        foreach (var call in response.ToolCalls)
        {
            _Logger.Information(
                "LLM tool_call: name={ToolName} argsLength={ArgsLength} args=\n{Arguments}",
                call.Name,
                call.Arguments.Length,
                call.Arguments);
            await _RunToolCallAsync(call, cancellationToken).ConfigureAwait(false);
        }
    }

    private void _NotifyHttpResponseUsage(LlmChatOptions chatOptions, int round, LlmUsage responseUsage)
    {
        if (_OnReceiveHttpResponse == null)
        {
            return;
        }

        var report = new LlmSessionUsageReport(
            responseUsage,
            _CumulativeLlmUsage,
            chatOptions.EnableReasoning,
            chatOptions.ReasoningEffort,
            round,
            _MaxToolRounds);
        _OnReceiveHttpResponse.Invoke(report);
    }

    private static bool _CheckContainsToolCalls(LlmResponse response)
    {
        return response.ToolCalls.Count > 0;
    }

    private string _GetLastAssistantTextFromHistory()
    {
        for (var i = _History.Count - 1; i >= 0; i--)
        {
            var message = _History[i];
            if (message.Role == LlmParticipantRole.Assistant)
            {
                return message.Content;
            }
        }

        return string.Empty;
    }

    private LlmChat _FinishWithAssistantTextOnly(LlmResponse response, LlmUsage chatUsage)
    {
        _History.Add(LlmMessage.CreateAssistant(
            response.Text,
            Array.Empty<ToolCall>(),
            response.ReasoningText ?? ""));

        return new LlmChat(response.Text, chatUsage);
    }

    private async Task _RunToolCallAsync(ToolCall call, CancellationToken cancellationToken)
    {
        if (!_TryCloneToolArgumentsRoot(call, out var argumentsCopy, out var parseError))
        {
            _Logger.Warning(
                "LLM tool_call invalid JSON: name={ToolName} error={Error}",
                call.Name,
                parseError);
            _History.Add(LlmMessage.CreateTool(call.ToolCallID, $"Invalid tool arguments JSON: {parseError}"));
            return;
        }

        var toolOutput = await _ToolRegistry
            .RunAsync(_ToolExecution, call.Name, argumentsCopy, cancellationToken)
            .ConfigureAwait(false);

        _Logger.Information(
            "LLM tool_result: name={ToolName} outputLength={OutputLength} output=\n{Output}",
            call.Name,
            toolOutput.Length,
            toolOutput);

        _History.Add(LlmMessage.CreateTool(call.ToolCallID, toolOutput));
    }

    private static bool _TryCloneToolArgumentsRoot(ToolCall call, out JsonElement argumentsRoot, out string errorMessage)
    {
        argumentsRoot = default;
        errorMessage = string.Empty;
        try
        {
            using var argumentsDocument = JsonDocument.Parse(string.IsNullOrWhiteSpace(call.Arguments) ? "{}" : call.Arguments);
            argumentsRoot = argumentsDocument.RootElement.Clone();
            return true;
        }
        catch (JsonException ex)
        {
            errorMessage = ex.Message;
            return false;
        }
    }

    #endregion Private Methods

    private class ToolRoundStep
    {
        public LlmUsage ChatUsage { get; init; }

        public LlmChat? CompletedResult { get; init; }
    }
}
