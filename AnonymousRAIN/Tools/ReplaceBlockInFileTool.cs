using System.Text.Json;

namespace ProofAgent.Tools;

public class ReplaceBlockInFileTool : ITool
{
    #region Fields

    private static readonly JsonSerializerOptions _JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    private const string _DeclarationRelativePath = "ToolDeclarations/replace_block_in_file.json";

    private readonly ToolDeclarationLoader _DeclarationLoader;

    #endregion Fields

    #region Properties

    public string Name => "replace";

    #endregion Properties

    public ReplaceBlockInFileTool(ToolDeclarationLoader declarationLoader)
    {
        _DeclarationLoader = declarationLoader ?? throw new ArgumentNullException(nameof(declarationLoader));
    }

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
            var dto = JsonSerializer.Deserialize<ReplaceDto>(arguments, _JsonOptions);
            var validationError = _ValidateArguments(dto);
            if (validationError != null)
            {
                return Task.FromResult(validationError);
            }

            context.Replace(dto!.Path, dto.OldText, dto.NewText);

            return Task.FromResult("ok");
        }
        catch (Exception exception)
        {
            return Task.FromResult(exception.Message);
        }
    }

    #region Private Methods

    private static string? _ValidateArguments(ReplaceDto? dto)
    {
        if (dto == null || string.IsNullOrWhiteSpace(dto.Path))
        {
            return "Missing required parameter: path.";
        }

        if (dto.OldText == null)
        {
            return "Missing required parameter: oldText.";
        }

        if (dto.NewText == null)
        {
            return "Missing required parameter: newText.";
        }

        if (dto.OldText.Length == 0)
        {
            return "Invalid parameter: oldText must not be empty.";
        }

        return null;
    }

    private class ReplaceDto
    {
        public string Path { get; set; } = "";

        public string OldText { get; set; } = "";

        public string NewText { get; set; } = "";
    }

    #endregion Private Methods
}
