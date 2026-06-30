using ProofAgent.Llm;

namespace ProofAgent.Session;

public interface ILlmSession
{
    IReadOnlyList<LlmMessage> History { get; }

    Task<LlmChat> ChatAsync(string userMessage, LlmChatOptions chatOptions, CancellationToken cancellationToken);
}
