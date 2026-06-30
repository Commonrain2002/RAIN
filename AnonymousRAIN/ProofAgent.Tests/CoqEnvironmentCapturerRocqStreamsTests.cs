using ProofAgent.Coq;
using ProofAgent.Tests.Fakes;
using ProofAgent.Tools;
using Xunit;

namespace ProofAgent.Tests;

/// <summary>Redirect Show auxiliary output file read and Coq string escaping.</summary>
public class CoqEnvironmentCapturerRocqStreamsTests
{
    private static readonly Type _CoqEnvironmentCapturerType = typeof(CoqEnvironmentCapturer);

    [Fact]
    public void EscapePathForCoqStringLiteral_EscapesQuotesAndUsesForwardSlashes()
    {
        var escaped = ReflectionTestAccess.InvokeStaticNonPublic<string>(
            _CoqEnvironmentCapturerType,
            "_EscapePathForCoqStringLiteral",
            new object?[] { @"C:\tmp\_ProofAgent_Aux_Environment_abc""x" });
        Assert.Equal("C:/tmp/_ProofAgent_Aux_Environment_abc\\\"x", escaped);
    }

    [Fact]
    public void TryReadRedirectShowOutputFile_ReadsTrimmedContent()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCapturerUnit_" + Guid.NewGuid().ToString("N", null));
        Directory.CreateDirectory(root);
        try
        {
            var fileSystem = new ProjectFileSystem(root);
            var ownedStem = "_ProofAgent_Aux_Environment_test_" + Guid.NewGuid().ToString("N", null);
            var ownedOutput = fileSystem.CreateTempFile(ownedStem + ".out");
            File.WriteAllText(ownedOutput.FullPath, "\n  1 goal\n  ============================\n  True\n  \n");
            var capturer = _CreateCapturer(fileSystem);
            var env = ReflectionTestAccess.InvokeInstanceNonPublic<string>(
                capturer,
                "_ReadEnvironmentOutputFile",
                new object?[] { ownedOutput });
            Assert.Contains("1 goal", env, StringComparison.Ordinal);
            Assert.Contains("============================", env, StringComparison.Ordinal);
            Assert.Contains("True", env, StringComparison.Ordinal);
        }
        finally
        {
            try
            {
                Directory.Delete(root, recursive: true);
            }
            catch
            {
                // best-effort
            }
        }
    }

    [Fact]
    public void TryReadRedirectShowOutputFile_MissingOutFile_ReturnsEmpty()
    {
        var root = Path.Combine(Path.GetTempPath(), "ProofAgentCapturerUnit_" + Guid.NewGuid().ToString("N", null));
        Directory.CreateDirectory(root);
        try
        {
            var fileSystem = new ProjectFileSystem(root);
            var ownedStem = "_ProofAgent_Aux_Environment_missing_" + Guid.NewGuid().ToString("N", null);
            var ownedOutput = fileSystem.CreateTempFile(ownedStem + ".out");
            var capturer = _CreateCapturer(fileSystem);
            var env = ReflectionTestAccess.InvokeInstanceNonPublic<string>(
                capturer,
                "_ReadEnvironmentOutputFile",
                new object?[] { ownedOutput });
            Assert.Equal("", env);
        }
        finally
        {
            try
            {
                Directory.Delete(root, recursive: true);
            }
            catch
            {
                // best-effort
            }
        }
    }

    [Fact]
    public void BuildEnvironmentProbeRedirectSentence_UsesRedirectShowForm()
    {
        var outputPath = new AbsolutePath("/tmp/_ProofAgent_Aux_Environment_deadbeef.out");
        var sentence = ReflectionTestAccess.InvokeStaticNonPublic<string>(
            _CoqEnvironmentCapturerType,
            "_BuildEnvironmentProbe",
            new object?[] { outputPath });
        Assert.Equal("Redirect \"/tmp/_ProofAgent_Aux_Environment_deadbeef\" Show.", sentence);
    }

    private static CoqEnvironmentCapturer _CreateCapturer(ProjectFileSystem fileSystem)
    {
        var logger = TestInjectedLogger.CreateFatalOnly();
        return new CoqEnvironmentCapturer(
            fileSystem,
            new QueueCoqProjectChecker(Array.Empty<CoqCheck>()),
            new NullCoqSentenceAnalyzer(),
            60,
            "make",
            logger);
    }
}
