using System.Text.Json;

namespace ProofAgent.Tools;

public class ReadFileTool : ITool
{
    #region Fields

    private const string _DeclarationRelativePath = "ToolDeclarations/read_file.json";

    private readonly ToolDeclarationLoader _DeclarationLoader;

    private static readonly JsonSerializerOptions _JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    #endregion Fields

    public ReadFileTool(ToolDeclarationLoader declarationLoader)
    {
        _DeclarationLoader = declarationLoader ?? throw new ArgumentNullException(nameof(declarationLoader));
    }

    public string Name => "read_file";

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
            var dto = JsonSerializer.Deserialize<ReadFileDto>(arguments, _JsonOptions);
            var validationError = _ValidateArguments(dto);
            if (validationError != null)
            {
                return Task.FromResult(validationError);
            }

            return Task.FromResult(context.ReadFileRange(dto!.Path, dto.StartLine, dto.EndLine));
        }
        catch (Exception exception)
        {
            return Task.FromResult(exception.Message);
        }
    }

    #region Private Methods

    private static string? _ValidateArguments(ReadFileDto? dto)
    {
        if (dto == null || string.IsNullOrWhiteSpace(dto.Path))
        {
            return "Missing required parameter: path.";
        }

        if (dto.StartLine <= 0 || dto.EndLine <= 0)
        {
            return "startLine/endLine must be 1-based positive integers.";
        }

        if (dto.StartLine > dto.EndLine)
        {
            return "startLine must be <= endLine.";
        }

        return null;
    }

    private class ReadFileDto
    {
        public string Path { get; set; } = "";

        public int StartLine { get; set; }

        public int EndLine { get; set; }
    }

    #endregion Private Methods
}
