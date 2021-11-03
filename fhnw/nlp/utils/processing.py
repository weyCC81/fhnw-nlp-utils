from sklearn.base import TransformerMixin, BaseEstimator

# https://towardsdatascience.com/make-your-own-super-pandas-using-multiproc-1c04f41944a1
# https://www.digitalocean.com/community/tutorials/how-to-use-args-and-kwargs-in-python-3
# https://stackoverflow.com/a/28975239
# http://python.omics.wiki/multiprocessing_map/multiprocessing_partial_function_multiple_arguments
# https://stackoverflow.com/questions/45545110/make-pandas-dataframe-apply-use-all-cores
class Preprocessor(BaseEstimator, TransformerMixin):
    
    def __init__(self, func, **func_params):
        """        
        func : function
            The function to apply
        func_params : The function parameters
            All the parameters for the provided function 'func'. 
            Additionally, 'func_params' can contain following control parameters:
            - 'n_jobs' specifies the exact number of processes to spawn (defaults to 'psutil.cpu_count(logical=True)').
            - 'field_read' specifies the data column name to read. If this parameter is undefined, the complete row is passed to 'func' (can be usefull if func needs to read several values)
            - 'raw' specifies if a raw numpy array (only row wise processing) will be provided to 'func' (defaults to 'False').
            - 'field_write' specifies the column name to write the result of 'func' (defaults to 'output'). 
            - 'finalizer_func' specifies the final function that should be applied to the original dataframe and the newly computed series (defaults to the concatenation using the 'field_write' as the name of the new column 'provide_concated_dfs(original_df, computed_series, field_write)'. Other provided alternatives are 'provide_computed_df' and 'provide_computed_series_as_list')
        """
        self.func = func
        self.func_params = func_params

    def fit(self, X, y=None):
        return self

    def transform(self, X, *_):
        return parallelize_dataframe(X, self.func, **self.func_params)
    
    def predict(self, X, **predict_params):
        return parallelize_dataframe(X, self.func, **self.func_params)      


def parallelize_dataframe(df, func, **func_params):
    """Breaks a pandas dataframe in n_jobs parts and spawns n_jobs processes to apply the provided function to all the parts

    Parameters
    ----------
    df : dataframe
        The dataframe with the data
    func : function
        The function to apply
    func_params : The function parameters
        All the parameters for the provided function 'func'. 
        Additionally, 'func_params' can contain following control parameters:
        - 'n_jobs' specifies the exact number of processes to spawn (defaults to 'psutil.cpu_count(logical=True)').
        - 'field_read' specifies the data column name to read. If this parameter is undefined, the complete row is passed to 'func' (can be usefull if func needs to read several values)
        - 'raw' specifies if a raw numpy array (only row wise processing) will be provided to 'func' (defaults to 'False').
        - 'field_write' specifies the column name to write the result of 'func' (defaults to 'output'). 
        - 'finalizer_func' specifies the final function that should be applied to the original dataframe and the newly computed series (defaults to the concatenation using the 'field_write' as the name of the new column 'provide_concated_dfs(original_df, computed_series, field_write)'. Other provided alternatives are 'provide_computed_df' and 'provide_computed_series_as_list')

    Returns
    -------
    dataframe
        A dataframe with the result of the function call (or the original dataframe concatenated with the processing result in case 'field_read' was not provided)
    """

    # https://towardsdatascience.com/make-your-own-super-pandas-using-multiproc-1c04f41944a1
    # https://www.digitalocean.com/community/tutorials/how-to-use-args-and-kwargs-in-python-3
    # https://stackoverflow.com/a/28975239
    # http://python.omics.wiki/multiprocessing_map/multiprocessing_partial_function_multiple_arguments
    # https://stackoverflow.com/questions/45545110/make-pandas-dataframe-apply-use-all-cores
    # https://github.com/jmcarpenter2/swifter (an alternative)
    from multiprocess import Pool
    from functools import partial
    import numpy as np
    import pandas as pd

    finalizer_func = func_params.pop("finalizer_func", provide_concated_dfs)
    n_jobs = func_params.pop("n_jobs", -1)
    if n_jobs <= 0:
        import psutil
        n_jobs = psutil.cpu_count(logical=True)
    field_write = func_params.pop("field_write", "output") 
    raw = func_params.pop("raw", False)
    field_read = func_params.get("field_read")
    if field_read is not None:
        # only keep specific field -> less copying
        read_df = df[field_read].to_frame(field_read)
        # remove param
        func_params.pop("field_read")
        # prepare function
        sub_func_with_params = partial(func, **func_params)
        func_with_params = partial(_transform_sub_df_by_field, field_read, sub_func_with_params)
    else:
        read_df = df
        # prepare function
        func_with_params = partial(_transform_sub_df_by_row, raw, func, func_params)
    
    df_split = np.array_split(read_df, n_jobs)

    pool = Pool(n_jobs)
    write_df = pd.concat(pool.map(func_with_params, df_split))
    pool.close()
    pool.join()

    return finalizer_func(df, write_df, field_write)

def _transform_sub_df_by_field(field_read, func_with_params, df):
    #series = df[self.field_read].apply(self.func, args=self.func_params)
    series = df[field_read].map(func_with_params)
    #return series.to_frame(field_write)
    return series

def _transform_sub_df_by_row(raw, func, func_params, df):   
    series = df.apply(func, axis=1, raw=raw, args=func_params)
    #return series.to_frame(field_write)
    return series

def provide_concated_dfs(original_df, computed_series, field_write):
    """Concatenates the original dataframe with the computed series using 'field_write' as column name

    Parameters
    ----------
    original_df : dataframe
        The original dataframe
    computed_series : series
        The computed series
    field_write : The provided name of the computed series/column name
    
    Returns
    -------
    dataframe
        A concatenated dataframe 
    """
    return pd.concat([df, computed_series.to_frame(field_write)], axis=1)

def provide_computed_df(original_df, computed_series, field_write):
    """Creates a dataframe from the computed series using 'field_write' as column name

    Parameters
    ----------
    original_df : dataframe
        The original dataframe
    computed_series : series
        The computed series
    field_write : The provided name of the computed series/column name
    
    Returns
    -------
    dataframe
        A dataframe consisting of one column with the computation results
    """
    return computed_series.to_frame(field_write)

def provide_computed_series_as_list(original_df, computed_series, field_write):
    """Creates a list from the computed series

    Parameters
    ----------
    original_df : dataframe
        The original dataframe
    computed_series : series
        The computed series
    field_write : The provided name of the computed series/column name
    
    Returns
    -------
    list
        A list with the computation results
    """
    return computed_series.to_list()
        

def is_iterable(obj):
    """Checks if an object is iterable

    Parameters
    ----------
    obj : object
        The object to check if it is iterable
        
    Returns
    -------
    bool
        True if the object is iterable, False otherwise
    """
    
    try:
        iter(obj)
        return True
    except TypeError:
        return False
        
        
def identity(x):
    """Identity function, returns the same object as it receives. 
    Serialization in python does not work with lambdas (therefore this function).

    Parameters
    ----------
    x : object
        The object to return
        
    Returns
    -------
    object
        The received object
    """
    return x
