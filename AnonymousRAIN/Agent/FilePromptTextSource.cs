using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Agent;

public class FilePromptTextSource : IPromptTextSource
{
    #region Fields

    private readonly IReadOnlyFileSystem _Store;

    private readonly ILogger _Logger;

    private readonly Dictionary<string, string> _Cache = new(StringComparer.Ordinal);

    #endregion Fields

    public FilePromptTextSource(IReadOnlyFileSystem store, ILogger logger)
    {
        _Store = store ?? throw new ArgumentNullException(nameof(store));
        _Logger = logger ?? throw new ArgumentNullException(nameof(logger));

        var promptsRoot = _Store.Root;
        if (!_Store.DirectoryExists(promptsRoot))
        {
            _Logger.Error("Prompts directory not found: {PromptsRoot}", promptsRoot.FullPath);
            throw new DirectoryNotFoundException($"Prompts directory not found: {promptsRoot.FullPath}");
        }
    }

    public string GetText(string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath))
        {
            throw new ArgumentException("Relative path is required.", nameof(relativePath));
        }

        var rel = new RelativePath(relativePath, _Store.Root);
        var cacheKey = rel.PosixPath;
        if (_Cache.TryGetValue(cacheKey, out var cached))
        {
            return cached;
        }

        if (!_Store.Exists(rel))
        {
            var fullPath = rel.ToAbsolute().FullPath;
            _Logger.Error("Prompt file not found: {PromptPath}", fullPath);
            throw new FileNotFoundException($"Prompt file not found: {fullPath}", fullPath);
        }

        var text = _Store.ReadAllText(rel);
        _Cache[cacheKey] = text;
        return _Cache[cacheKey];
    }
}
