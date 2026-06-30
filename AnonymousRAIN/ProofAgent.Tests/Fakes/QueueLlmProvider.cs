using System.Collections.Concurrent;
using System.Text.Json;
using ProofAgent.Llm;

namespace ProofAgent.Tests.Fakes;

public class QueueLlmProvider : ILlmProvider
{
    private readonly ConcurrentQueue<LlmResponse> _Responses = new();

    public void Enqueue(LlmResponse response)
    {
        _Responses.Enqueue(response);
    }

    public Task<LlmResponse> ChatAsync(
        IReadOnlyList<LlmMessage> messages,
        IReadOnlyList<JsonElement> toolDeclarations,
        LlmChatOptions chatOptions,
        CancellationToken cancellationToken)
    {
        if (!_Responses.TryDequeue(out var response))
        {
            throw new InvalidOperationException("QueueLlmProvider: no more queued responses.");
        }

        return Task.FromResult(response);
    }
}
