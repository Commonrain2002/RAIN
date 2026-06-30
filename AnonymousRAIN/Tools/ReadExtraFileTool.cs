using System.Text.Json;

namespace ProofAgent.Tools;

public class ReadExtraFileTool : ITool
{
    #region Fields

    private const string _DeclarationRelativePath = "ToolDeclarations/read_external.json";

    private readonly ToolDeclarationLoader _DeclarationLoader;

    private static readonly JsonSerializerOptions _JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    #endregion Fields

    public ReadExtraFileTool(ToolDeclarationLoader declarationLoader)
    {
        _DeclarationLoader = declarationLoader ?? throw new ArgumentNullException(nameof(declarationLoader));
    }

    public string Name => "read_external";

    public JsonElement GetDeclaration()
    {
        return _DeclarationLoader.GetDeclaration(_DeclarationRelativePath);
    }

    public Task<string> RunAsync(
        IToolExecutionContext context,
        JsonElement arguments,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        try
        {
            var dto = JsonSerializer.Deserialize<ReadExtraFileDto>(arguments, _JsonOptions);
            if (dto == null || string.IsNullOrWhiteSpace(dto.Path))
            {
                return Task.FromResult("Missing required parameter: path.");
            }

            return Task.FromResult(context.ReadExtraFileRange(dto.Path, dto.StartLine, dto.EndLine));
        }
        catch (Exception exception)
        {
            return Task.FromResult(exception.Message);
        }
    }

    private class ReadExtraFileDto
    {
        public string Path { get; set; } = "";

        public int StartLine { get; set; }

        public int EndLine { get; set; }
    }
}
