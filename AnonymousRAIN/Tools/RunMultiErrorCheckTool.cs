using System.Text.Json;

namespace ProofAgent.Tools;

public class RunMultiErrorCheckTool : ITool
{
    #region Fields

    private const string _DeclarationRelativePath = "ToolDeclarations/run_multi_error_check.json";

    private readonly ToolDeclarationLoader _DeclarationLoader;

    #endregion Fields

    public RunMultiErrorCheckTool(ToolDeclarationLoader declarationLoader)
    {
        _DeclarationLoader = declarationLoader ?? throw new ArgumentNullException(nameof(declarationLoader));
    }

    public string Name => "run_check";

    public JsonElement GetDeclaration()
    {
        return _DeclarationLoader.GetDeclaration(_DeclarationRelativePath);
    }

    public async Task<string> RunAsync(
        IToolExecutionContext context,
        JsonElement arguments,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        try
        {
            return await context.RunMultiErrorCheckAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (Exception exception)
        {
            return exception.Message;
        }
    }
}
