using ProofAgent.Coq;
using Xunit;

namespace ProofAgent.Tests;

public class CoqCheckerMakeOutputFilterTests
{
    [Fact]
    public void FilterMakeRecursiveErrorSummaryLines_RemovesMakeJobSummaries_KeepsCoqError()
    {
        var raw = """
                  coqc backend/Foo.vo
                  File "Foo.v", line 2, characters 0-1:
                  Error: test.
                  make[1]: *** [Makefile:317: backend/Foo.vo] Error 1
                  make: *** [Makefile:243: all] Error 2
                  """;

        var filtered = _InvokeFilterMakeRecursiveErrorSummaryLines(raw);
        Assert.Contains("File \"Foo.v\"", filtered, StringComparison.Ordinal);
        Assert.Contains("Error: test.", filtered, StringComparison.Ordinal);
        Assert.DoesNotContain("make[1]:", filtered, StringComparison.Ordinal);
        Assert.DoesNotContain("make:", filtered, StringComparison.Ordinal);
        Assert.DoesNotContain("Makefile:317", filtered, StringComparison.Ordinal);
        Assert.DoesNotContain("Makefile:243", filtered, StringComparison.Ordinal);
    }

    [Fact]
    public void FilterMakeRecursiveErrorSummaryLines_RemovesTopLevelMakefileTargetLine()
    {
        var raw = """
                  coqc theories/Foo.v
                  File "theories/Foo.v", line 1, characters 0-1:
                  Error: test.
                  make: *** [Makefile:8: core] Error 1
                  """;

        var filtered = _InvokeFilterMakeRecursiveErrorSummaryLines(raw);
        Assert.Contains("File \"theories/Foo.v\"", filtered, StringComparison.Ordinal);
        Assert.DoesNotContain("Makefile:8", filtered, StringComparison.Ordinal);
        Assert.DoesNotContain("make:", filtered, StringComparison.Ordinal);
    }

    [Fact]
    public void FilterMakeRecursiveErrorSummaryLines_RemovesParallelMakeIgnoredSuffix()
    {
        var raw = "make: *** [Makefile:1: all] Error 2 (ignored)";
        var filtered = _InvokeFilterMakeRecursiveErrorSummaryLines(raw);
        Assert.Equal("", filtered);
    }

    [Fact]
    public void FilterMakeRecursiveErrorSummaryLines_RemovesDeletingFileEchoLine()
    {
        var raw = """
                  File "flocq/Core/Ulp.v", line 1, characters 0-1:
                  Error: test.
                  make[2]: *** [Makefile.coq:838: flocq/Core/Ulp.vo] Error 1
                  make[2]: *** [flocq/Core/Ulp.vo] Deleting file 'flocq/Core/Ulp.glob'
                  """;

        var filtered = _InvokeFilterMakeRecursiveErrorSummaryLines(raw);
        Assert.Contains("Error: test.", filtered, StringComparison.Ordinal);
        Assert.DoesNotContain("make[2]:", filtered, StringComparison.Ordinal);
        Assert.DoesNotContain("Deleting file", filtered, StringComparison.Ordinal);
    }

    [Fact]
    public void FilterMakeRecursiveErrorSummaryLines_KeepsNonBracketMakeFailures()
    {
        var raw = "make: *** No rule to make target 'all'. Stop.";
        var filtered = _InvokeFilterMakeRecursiveErrorSummaryLines(raw);
        Assert.Equal(raw, filtered);
    }

    [Fact]
    public void FilterMakeRecursiveErrorSummaryLines_NullOrEmpty_IsSafe()
    {
        Assert.Equal("", _InvokeFilterMakeRecursiveErrorSummaryLines(null));
        Assert.Equal("", _InvokeFilterMakeRecursiveErrorSummaryLines(""));
        Assert.Equal("", _InvokeFilterMakeRecursiveErrorSummaryLines("   "));
    }

    private static string _InvokeFilterMakeRecursiveErrorSummaryLines(string? raw)
    {
        return ReflectionTestAccess.InvokeStaticNonPublic<string>(
                   typeof(CoqChecker),
                   "_FilterMakeSummaryLines",
                   new object?[] { raw })
               ?? "";
    }
}
