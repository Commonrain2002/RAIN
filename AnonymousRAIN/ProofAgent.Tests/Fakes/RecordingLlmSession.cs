using ProofAgent.Llm;
using ProofAgent.Session;

namespace ProofAgent.Tests.Fakes;

/// <summary>Records last <see cref="ILlmSession.ChatAsync"/> call arguments.</summary>
public class RecordingLlmSession : ILlmSession
{
    private readonly LlmChat _Result;

    public RecordingLlmSession(LlmChat? result = null)
    {
        _Result = result ?? new LlmChat("recorded");
    }

    public IReadOnlyList<LlmMessage> History { get; } = Array.Empty<LlmMessage>();

    public string? LastUserMessage { get; private set; }

    public LlmChatOptions? LastChatOptions { get; private set; }

    public Task<LlmChat> ChatAsync(string userMessage, LlmChatOptions chatOptions, CancellationToken cancellationToken)
    {
        LastUserMessage = userMessage;
        LastChatOptions = chatOptions;
        return Task.FromResult(_Result);
    }
}
