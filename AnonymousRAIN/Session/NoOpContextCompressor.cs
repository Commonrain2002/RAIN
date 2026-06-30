using ProofAgent.Llm;

namespace ProofAgent.Session;

public class NoOpContextCompressor : IContextCompressor
{
    public IReadOnlyList<LlmMessage> Compress(IReadOnlyList<LlmMessage> messages)
    {
        return messages;
    }
}
