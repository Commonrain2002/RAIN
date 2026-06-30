using ProofAgent.Coq;
using ProofAgent.Tools;
using Serilog;
using Xunit;

namespace ProofAgent.Tests;

public class CoqCheckerTests
{
    [Fact]
    public void TryExtractFirstCoqError_ParsesTypicalErrorBlock()
    {
        var output = """
                     coqc Foo/Bar.v
                     File "Foo/Bar.v", line 12, characters 3-10:
                     Error: The reference baz was not found in the current environment.
                     make: *** [Makefile:10: all] Error 1
                     """;

        var err = _InvokeTryExtractFirstCoqError(output);
        Assert.NotNull(err);
        Assert.Equal("Foo/Bar.v", err!.RelativeFilePath!.PosixPath);
        Assert.Equal(12, err.Line);
        Assert.Equal(3, err.Column);
        Assert.Contains("baz", err.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void TryExtractFirstCoqError_MultilineMessage_IsCaptured()
    {
        var output = """
                     File "A.v", line 5, characters 0-2:
                     Error: Unable to unify "x" with "y".
                     In environment
                     n : nat
                     m : nat
                     File "B.v", line 1, characters 0-1:
                     Error: Another error.
                     """;

        var err = _InvokeTryExtractFirstCoqError(output);
        Assert.NotNull(err);
        Assert.Equal("A.v", err!.RelativeFilePath!.PosixPath);
        Assert.Equal(5, err.Line);
        Assert.Equal(0, err.Column);
        Assert.Contains("Unable to unify", err.Message, StringComparison.Ordinal);
        Assert.Contains("In environment", err.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("Another error", err.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void TryExtractFirstCoqError_NoMatch_ReturnsNull()
    {
        var output = "make: *** No rule to make target 'all'. Stop.";
        Assert.Null(_InvokeTryExtractFirstCoqError(output));
    }

    [Fact]
    public void TryExtractFirstCoqError_TrailingMakeJobSummaryLines_NotIncludedInMessage()
    {
        var output = """
                     File "backend/LLVMInstCombineproof.v", line 132, characters 29-30:
                     Error: Nothing to rewrite.

                     make[1]: *** [Makefile:317: backend/LLVMInstCombineproof.vo] Error 1
                     make: *** [Makefile:243: all] Error 2
                     """;

        var err = _InvokeTryExtractFirstCoqError(output);
        Assert.NotNull(err);
        Assert.Contains("Nothing to rewrite", err!.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("make[1]:", err.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("Makefile:317", err.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("Makefile:243", err.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void TryExtractFirstCoqError_DeletingFileEchoLine_NotIncludedInMessage()
    {
        var output = """
                     File "flocq/Core/Ulp.v", line 2454, characters 30-31:
                     Error: This proof is focused, but cannot be unfocused this way

                     make[2]: *** [Makefile.coq:838: flocq/Core/Ulp.vo] Error 1
                     make[2]: *** [flocq/Core/Ulp.vo] Deleting file 'flocq/Core/Ulp.glob'
                     """;

        var filtered = ReflectionTestAccess.InvokeStaticNonPublic<string>(
            typeof(CoqChecker),
            "_FilterMakeSummaryLines",
            new object?[] { output }) ?? "";
        var err = _InvokeTryExtractFirstCoqError(filtered);
        Assert.NotNull(err);
        Assert.Contains("cannot be unfocused", err!.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("make[2]:", err.Message, StringComparison.Ordinal);
        Assert.DoesNotContain("Deleting file", err.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task CheckAsync_CustomShellLineTrue_SucceedsOnLinux()
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        var logger = TestInjectedLogger.CreateFatalOnly();
        var tmp = Path.Combine(Path.GetTempPath(), "ProofAgentCoqCheck_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tmp);
        var checker = new CoqChecker(
            logger,
            new ProcessRunner(),
            new AbsolutePath(tmp),
            new CoqProofSkipFinder(new ProjectFileSystem(tmp)));
        try
        {
            var result = await checker.CheckAsync(null, 10, "true", CancellationToken.None);
            Assert.True(result.Success);
        }
        finally
        {
            try
            {
                Directory.Delete(tmp, recursive: true);
            }
            catch
            {
                // Ignore cleanup failures
            }
        }
    }

    private static CoqError? _InvokeTryExtractFirstCoqError(string? output)
    {
        return ReflectionTestAccess.InvokeStaticNonPublic<CoqError?>(
            typeof(CoqChecker),
            "_TryExtractFirstCoqError",
            new object?[] { output, new AbsolutePath(Path.GetTempPath()) });
    }
}

