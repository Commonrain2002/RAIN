using System.Text.Json;
using System.Text.RegularExpressions;

namespace ProofAgent.Tools;

public class SearchExtraByRegexTool : ITool
{
    #region Fields

    private const int _DefaultMaxMatches = 250;

    private const string _DeclarationRelativePath = "ToolDeclarations/search_external.json";

    private readonly ToolDeclarationLoader _DeclarationLoader;

    private static readonly JsonSerializerOptions _JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    #endregion Fields

    #region Properties

    public string Name => "search_external";

    #endregion Properties

    public SearchExtraByRegexTool(ToolDeclarationLoader declarationLoader)
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
            var dto = JsonSerializer.Deserialize<SearchExtraByRegexDto>(arguments, _JsonOptions);
            var validationError = _ValidateArguments(dto, out var maxMatches, out var offset);
            if (validationError != null)
            {
                return Task.FromResult(validationError);
            }

            Regex regex;
            try
            {
                var opts = RegexOptions.CultureInvariant;
                if (dto!.CaseInsensitive)
                {
                    opts |= RegexOptions.IgnoreCase;
                }

                regex = new Regex(dto.Pattern.Trim(), opts);
            }
            catch (ArgumentException exception)
            {
                return Task.FromResult($"Invalid regular expression: {exception.Message}");
            }

            return Task.FromResult(context.SearchExtraByRegex(regex, offset, maxMatches, dto.IsShowContext));
        }
        catch (Exception exception)
        {
            return Task.FromResult(exception.Message);
        }
    }

    #region Private Methods

    private static string? _ValidateArguments(
        SearchExtraByRegexDto? dto,
        out int maxMatches,
        out int offset)
    {
        maxMatches = _DefaultMaxMatches;
        offset = 0;

        if (dto == null || string.IsNullOrWhiteSpace(dto.Pattern))
        {
            return "Missing required parameter: pattern.";
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

    private class SearchExtraByRegexDto
    {
        public string Pattern { get; set; } = "";

        public bool CaseInsensitive { get; set; }

        public int MaxMatches { get; set; }

        public int Offset { get; set; }

        public bool IsShowContext { get; set; }
    }

    #endregion Private Methods
}
