using System.Text.Json;

namespace ProofAgent.Tools;

public class ReadLemmaInFileTool : ITool
{
    #region Fields

    private const int _DefaultMaxMatches = 250;

    private const string _DeclarationRelativePath = "ToolDeclarations/read_lemma.json";

    private readonly ToolDeclarationLoader _DeclarationLoader;

    private static readonly JsonSerializerOptions _JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    #endregion Fields

    #region Properties

    public string Name => "read_lemma";

    #endregion Properties

    public ReadLemmaInFileTool(ToolDeclarationLoader declarationLoader)
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
            var dto = JsonSerializer.Deserialize<ReadLemmaInFileDto>(arguments, _JsonOptions);
            var validationError = _ValidateArguments(dto, out var maxMatches, out var offset);
            if (validationError != null)
            {
                return Task.FromResult(validationError);
            }

            return Task.FromResult(context.ReadLemmasInFile(dto!.Path.Trim(), offset, maxMatches));
        }
        catch (Exception exception)
        {
            return Task.FromResult(exception.Message);
        }
    }

    #region Private Methods

    private static string? _ValidateArguments(
        ReadLemmaInFileDto? dto,
        out int maxMatches,
        out int offset)
    {
        maxMatches = _DefaultMaxMatches;
        offset = 0;

        if (dto == null || string.IsNullOrWhiteSpace(dto.Path))
        {
            return "Missing required parameter: path.";
        }

        maxMatches = dto.MaxMatches <= 0 ? _DefaultMaxMatches : dto.MaxMatches;
        if (maxMatches <= 0)
        {
            return "maxMatches must be a positive integer.";
        }

        if (dto.Offset < 0)
        {
            return "offset must be a non-negative integer.";
        }

        offset = dto.Offset;
        return null;
    }

    private class ReadLemmaInFileDto
    {
        public string Path { get; set; } = "";

        public int MaxMatches { get; set; }

        public int Offset { get; set; }
    }

    #endregion Private Methods
}
