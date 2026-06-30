using System.Linq;
using System.Reflection;

namespace ProofAgent.Tests;

/// <summary>
/// Invokes non-public members via reflection for unit tests when production types keep helpers private.
/// </summary>
public class ReflectionTestAccess
{
    #region Fields

    private const BindingFlags _StaticNonPublic = BindingFlags.Static | BindingFlags.NonPublic;

    private const BindingFlags _InstanceNonPublic = BindingFlags.Instance | BindingFlags.NonPublic;

    #endregion Fields

    private ReflectionTestAccess()
    {
    }

    /// <summary>
    /// Pass arguments as <c>new object?[] { a, b }</c>; do not use <c>params</c> on the caller side with a <c>string[]</c>
    /// intended as a single argument (the compiler would expand it into multiple <c>object</c> slots).
    /// </summary>
    public static object? InvokeStaticNonPublic(Type declaringType, string methodName, object?[]? parameters)
    {
        if (declaringType == null)
        {
            throw new ArgumentNullException(nameof(declaringType));
        }

        if (string.IsNullOrEmpty(methodName))
        {
            throw new ArgumentException("methodName must not be empty.", nameof(methodName));
        }

        parameters ??= Array.Empty<object?>();
        var method = _FindBestMatchingStaticMethod(declaringType, methodName, parameters);
        if (method == null)
        {
            throw new InvalidOperationException(
                "No matching static non-public method '" + methodName + "' on " + declaringType.FullName + ".");
        }

        return method.Invoke(null, parameters);
    }

    public static T? InvokeStaticNonPublic<T>(Type declaringType, string methodName, object?[]? parameters)
    {
        var raw = InvokeStaticNonPublic(declaringType, methodName, parameters);
        if (raw == null)
        {
            return default;
        }

        return (T)raw;
    }

    public static object? InvokeInstanceNonPublic(object instance, string methodName, object?[]? parameters)
    {
        if (instance == null)
        {
            throw new ArgumentNullException(nameof(instance));
        }

        if (string.IsNullOrEmpty(methodName))
        {
            throw new ArgumentException("methodName must not be empty.", nameof(methodName));
        }

        parameters ??= Array.Empty<object?>();
        var method = _FindBestMatchingInstanceMethod(instance.GetType(), methodName, parameters);
        if (method == null)
        {
            throw new InvalidOperationException(
                "No matching instance non-public method '" + methodName + "' on " + instance.GetType().FullName + ".");
        }

        return method.Invoke(instance, parameters);
    }

    public static T? InvokeInstanceNonPublic<T>(object instance, string methodName, object?[]? parameters)
    {
        var raw = InvokeInstanceNonPublic(instance, methodName, parameters);
        if (raw == null)
        {
            return default;
        }

        return (T)raw;
    }

    public static T? GetStaticFieldNonPublic<T>(Type declaringType, string fieldName)
    {
        if (declaringType == null)
        {
            throw new ArgumentNullException(nameof(declaringType));
        }

        if (string.IsNullOrEmpty(fieldName))
        {
            throw new ArgumentException("fieldName must not be empty.", nameof(fieldName));
        }

        var field = declaringType.GetField(fieldName, _StaticNonPublic);
        if (field == null)
        {
            throw new InvalidOperationException(
                "Missing static non-public field '" + fieldName + "' on " + declaringType.FullName + ".");
        }

        return (T?)field.GetValue(null);
    }

    public static T? GetInstanceFieldNonPublic<T>(object instance, string fieldName)
    {
        if (instance == null)
        {
            throw new ArgumentNullException(nameof(instance));
        }

        if (string.IsNullOrEmpty(fieldName))
        {
            throw new ArgumentException("fieldName must not be empty.", nameof(fieldName));
        }

        var field = instance.GetType().GetField(fieldName, _InstanceNonPublic);
        if (field == null)
        {
            throw new InvalidOperationException(
                "Missing instance non-public field '" + fieldName + "' on " + instance.GetType().FullName + ".");
        }

        return (T?)field.GetValue(instance);
    }

    #region Private Methods


    private static MethodInfo? _FindBestMatchingStaticMethod(Type declaringType, string methodName, object?[] parameters)
    {
        return _FindBestMatchingMethod(declaringType, methodName, parameters, _StaticNonPublic);
    }

    private static MethodInfo? _FindBestMatchingInstanceMethod(Type declaringType, string methodName, object?[] parameters)
    {
        return _FindBestMatchingMethod(declaringType, methodName, parameters, _InstanceNonPublic);
    }

    private static MethodInfo? _FindBestMatchingMethod(
        Type declaringType,
        string methodName,
        object?[] parameters,
        BindingFlags bindingFlags)
    {
        var candidates = declaringType
            .GetMethods(bindingFlags)
            .Where(m => m.Name == methodName && m.GetParameters().Length == parameters.Length)
            .ToArray();

        if (candidates.Length == 0)
        {
            return null;
        }

        if (candidates.Length == 1)
        {
            return candidates[0];
        }

        foreach (var method in candidates)
        {
            if (_ParametersAssignable(method.GetParameters(), parameters))
            {
                return method;
            }
        }

        return null;
    }

    private static bool _ParametersAssignable(ParameterInfo[] formalParameters, object?[] actualArguments)
    {
        for (var i = 0; i < formalParameters.Length; i++)
        {
            var arg = actualArguments[i];
            if (arg == null)
            {
                if (!formalParameters[i].ParameterType.IsClass
                    && Nullable.GetUnderlyingType(formalParameters[i].ParameterType) == null)
                {
                    return false;
                }

                continue;
            }

            var argType = arg.GetType();
            if (!formalParameters[i].ParameterType.IsAssignableFrom(argType))
            {
                return false;
            }
        }

        return true;
    }

    #endregion Private Methods
}
