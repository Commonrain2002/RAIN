using System.Text.Json;

namespace ProofAgent.Llm;

public interface ILlmProvider
{
    Task<LlmResponse> ChatAsync(
        IReadOnlyList<LlmMessage> messages,
        IReadOnlyList<JsonElement> toolDeclarations,
        LlmChatOptions chatOptions,
        CancellationToken cancellationToken);
}
