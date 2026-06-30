using ProofAgent.Coq;
using ProofAgent.Tools;

namespace ProofAgent.Tests;

public static class ToolExecutionContextTestFixtures
{
    public static ToolExecutionContext CreateFileOnly(
        ProjectFileSystem fileSystem,
        int searchHitContextLines,
        LemmaDatabase? lemmaDatabase = null)
    {
        return new ToolExecutionContext(
            fileSystem,
            Array.Empty<IReadOnlyFileSystem>(),
            searchHitContextLines,
            UnusedRunCheckToolExecutionDependencies.MultiErrorChecker,
            UnusedRunCheckToolExecutionDependencies.RunCheckResultFormatter,
            lemmaDatabase ?? CreateEmptyLemmaDatabase());
    }

    public static LemmaDatabase CreateEmptyLemmaDatabase()
    {
        return new LemmaDatabase(TestInjectedLogger.CreateFatalOnly());
    }

    public static ToolExecutionContext CreateFileOnly(string projectRoot, int searchHitContextLines = 2)
    {
        return CreateFileOnly(new ProjectFileSystem(projectRoot), searchHitContextLines);
    }

    public static ToolExecutionContext CreateWithExtraReadableRoots(
        ProjectFileSystem fileSystem,
        IReadOnlyList<IReadOnlyFileSystem> extraReadableRootFileSystems,
        int searchHitContextLines = 2)
    {
        return new ToolExecutionContext(
            fileSystem,
            extraReadableRootFileSystems,
            searchHitContextLines,
            UnusedRunCheckToolExecutionDependencies.MultiErrorChecker,
            UnusedRunCheckToolExecutionDependencies.RunCheckResultFormatter,
            CreateEmptyLemmaDatabase());
    }

    public static ToolExecutionContext CreateWithRunCheck(
        ProjectFileSystem fileSystem,
        ICoqMultiErrorChecker multiErrorChecker,
        IRunCheckToolResultFormatter runCheckResultFormatter,
        int searchHitContextLines)
    {
        return new ToolExecutionContext(
            fileSystem,
            Array.Empty<IReadOnlyFileSystem>(),
            searchHitContextLines,
            multiErrorChecker,
            runCheckResultFormatter,
            CreateEmptyLemmaDatabase());
    }

    public static ToolExecutionContext CreateWithRunCheck(
        string projectRoot,
        ICoqMultiErrorChecker multiErrorChecker,
        IRunCheckToolResultFormatter runCheckResultFormatter,
        int searchHitContextLines = 2)
    {
        return CreateWithRunCheck(
            new ProjectFileSystem(projectRoot),
            multiErrorChecker,
            runCheckResultFormatter,
            searchHitContextLines);
    }
}

internal static class UnusedRunCheckToolExecutionDependencies
{
    private const string _NotConfiguredMessage =
        "Run multi-error check is not configured for this test ToolExecutionContext.";

    public static readonly ICoqMultiErrorChecker MultiErrorChecker = new UnusedCoqMultiErrorChecker();

    public static readonly IRunCheckToolResultFormatter RunCheckResultFormatter =
        new UnusedRunCheckToolResultFormatter();

    private sealed class UnusedCoqMultiErrorChecker : ICoqMultiErrorChecker
    {
        public Task<IReadOnlyList<CoqRunCheckFailure>> RunMultiErrorCheckAsync(CancellationToken cancellationToken)
        {
            throw new InvalidOperationException(_NotConfiguredMessage);
        }
    }

    private sealed class UnusedRunCheckToolResultFormatter : IRunCheckToolResultFormatter
    {
        public string FormatRunCheckFailures(IReadOnlyList<CoqRunCheckFailure> failures)
        {
            throw new InvalidOperationException(_NotConfiguredMessage);
        }
    }
}
