using System.Text.Json;

namespace ProofAgent.Tools;

public interface ITool
{
    string Name { get; }

    JsonElement GetDeclaration();

    Task<string> RunAsync(
        IToolExecutionContext context,
        JsonElement arguments,
        CancellationToken cancellationToken);
}
