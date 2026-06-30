using System.Collections.Concurrent;

using ProofAgent.Agent;
using ProofAgent.Tools;
using Serilog;

namespace ProofAgent.Tests;

public static class PromptTestFixtures
{
    private sealed class PromptWiring
    {
        public required FilePromptTextSource TextSource { get; init; }

        public required ToolDeclarationLoader ToolDeclarations { get; init; }

        public required RunCheckToolResultFormatter RunCheckFormatter { get; init; }
    }

    private static readonly ConcurrentDictionary<ILogger, PromptWiring> _WiringByLogger = new();

    public static string ResolvePromptsRoot()
    {
        return Path.Combine(AppContext.BaseDirectory, "Prompts");
    }

    public static FilePromptTextSource CreatePromptTextSource(ILogger logger)
    {
        return _GetWiring(logger).TextSource;
    }

    public static ToolDeclarationLoader CreateToolDeclarationLoader(ILogger logger)
    {
        return _GetWiring(logger).ToolDeclarations;
    }

    public static RunCheckToolResultFormatter CreateRunCheckToolResultFormatter(ILogger logger)
    {
        return _GetWiring(logger).RunCheckFormatter;
    }

    private static PromptWiring _GetWiring(ILogger logger)
    {
        return _WiringByLogger.GetOrAdd(logger, _CreateWiring);
    }

    private static PromptWiring _CreateWiring(ILogger logger)
    {
        var store = new ProjectFileSystem(ResolvePromptsRoot());
        var textSource = new FilePromptTextSource(store, logger);
        return new PromptWiring
        {
            TextSource = textSource,
            ToolDeclarations = new ToolDeclarationLoader(textSource),
            RunCheckFormatter = new RunCheckToolResultFormatter(textSource),
        };
    }
}
