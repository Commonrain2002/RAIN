using ProofAgent.Llm;
using ProofAgent.Session;

namespace ProofAgent.Tests.Fakes;

public class PassThroughContextCompressor : IContextCompressor
{
    public IReadOnlyList<LlmMessage> Compress(IReadOnlyList<LlmMessage> messages)
    {
        return messages;
    }
}
