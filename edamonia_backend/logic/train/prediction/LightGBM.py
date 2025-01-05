from sklearn.model_selection import train_test_split, GridSearchCV, TimeSeriesSplit, cross_val_score
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, make_scorer
import numpy as np
from edamonia_backend.logic.train.preprocess_data import preprocess_data, preprocess_test_data
import pandas as pd
import os
from sklearn.decomposition import PCA


def train(events, dataset_path):

    if events == 0:
        file_path = os.path.join(dataset_path, "dataset.csv")
        test_path = os.path.join(dataset_path, "test_dataset.csv")

        X_scaled, y = preprocess_data(file_path, 0)
        X_test, y_test = preprocess_data(test_path, 0)

        param_grid = {
            'n_estimators': [200],  # Кількість дерев
            'learning_rate': [0.1],  # Темп навчання
            'max_depth': [7],  # Глибина дерева
            'num_leaves': [15]  # Кількість листків
        }
    else:
        file_path = os.path.join(dataset_path, "dataset_event.csv")
        test_path = os.path.join(dataset_path, "test_dataset_event.csv")

        X_scaled, y = preprocess_data(file_path, 1)
        X_test, y_test = preprocess_data(test_path, 1)

        param_grid = {
            'n_estimators': [200],  # Кількість дерев
            'learning_rate': [0.1],  # Темп навчання
            'max_depth': [7],  # Глибина дерева
            'num_leaves': [15]  # Кількість листків
        }
    raw_test = pd.read_csv(test_path)

    noise_level = 0.1  # Налаштуйте рівень шуму за потреби
    np.random.seed(42)  # Для відтворюваності
    noise = np.random.normal(0, noise_level, X_scaled.shape)
    X_train = X_scaled + noise

    tscv = TimeSeriesSplit(n_splits=5)
    lgbm_model = LGBMRegressor(objective='regression', random_state=42, verbose=-1)

    # Step 4: Set up GridSearchCV
    grid_search = GridSearchCV(
        estimator=lgbm_model,
        param_grid=param_grid,
        scoring='neg_mean_squared_error',  # Оптимізація за MSE
        cv=tscv,
        n_jobs=12,
        verbose=1
    )

    # Step 5: Fit GridSearchCV
    grid_search.fit(X_train, y)

    # Step 6: Convert results to DataFrame and sort by mean_test_score
    results_df = pd.DataFrame(grid_search.cv_results_)
    results_df['mean_test_score'] = -results_df['mean_test_score']  # Convert MSE to positive for easier interpretation
    sorted_results = results_df.sort_values(by='mean_test_score').reset_index(drop=True)

    # Step 7: Select rows for the table
    selected_rows = sorted_results.iloc[
        [0, len(sorted_results) // 4, len(sorted_results) // 2, sorted_results['mean_test_score'].idxmin(), len(sorted_results) - 1]
    ]

    # Step 8: Create table for the article
    table = selected_rows[
        ['param_n_estimators', 'param_learning_rate', 'param_max_depth', 'param_num_leaves', 'mean_test_score', 'std_test_score']
    ].copy()
    table.columns = [
        'Кількість дерев', 'Темп навчання', 'Глибина дерева', 'Кількість листків',
        'Середнє MSE (крос-валідація)', 'Стандартне відхилення MSE'
    ]

    # Step 9: Compute R² for each selected model
    r2_scores = []
    for _, row in selected_rows.iterrows():
        model = LGBMRegressor(
            n_estimators=row['param_n_estimators'],
            learning_rate=row['param_learning_rate'],
            max_depth=row['param_max_depth'],
            num_leaves=row['param_num_leaves'],
            objective='regression',
            random_state=42,
            verbose=-1
        )
        r2 = cross_val_score(model, X_train, y, cv=tscv, scoring=make_scorer(r2_score)).mean()
        r2_scores.append(r2)

    # Step 10: Add R² column to the table
    table['R² (крос-валідація)'] = r2_scores

    # Step 11: Save table to CSV
    table.to_csv('edamonia_backend/logic/train/prediction_results/LightGBM_results.csv', index=False, encoding='utf-8-sig')

    # Step 11: Make predictions using the best model from GridSearchCV
    best_model = grid_search.best_estimator_
    # Step 7: Get the best model's parameters
    best_params = grid_search.best_params_
    best_score = -grid_search.best_score_
    best_r2 = cross_val_score(best_model, X_train, y, cv=tscv, scoring='r2').mean()

    # Step 8: Print the best model parameters
    print("\nПараметри найкращої моделі LightGBM:")
    print(f"Кількість ітерацій: {best_params['n_estimators']}")
    print(f"Темп навчання: {best_params['learning_rate']}")
    print(f"Максимальна глибина дерева: {best_params['max_depth']}")
    print(f"Кількість листків: {best_params['num_leaves']}")
    print(f"Середнє MSE (крос-валідація): {best_score:.4f}")
    print(f"R² найкращої моделі: {best_r2:.4f}")

    best_model.fit(X_train, y)

    y_test_pred = best_model.predict(X_test)

    # Step 14: Calculate evaluation metrics for the test set
    test_mse = mean_squared_error(y_test, y_test_pred)
    test_rmse = np.sqrt(test_mse)
    test_mae = mean_absolute_error(y_test, y_test_pred)
    test_r2 = r2_score(y_test, y_test_pred)

    print("\nTest Set Metrics:")
    print(f"Mean Squared Error (MSE): {test_mse:.4f}")
    print(f"Root Mean Squared Error (RMSE): {test_rmse:.4f}")
    print(f"Mean Absolute Error (MAE): {test_mae:.4f}")
    print(f"R-squared (R²): {test_r2:.4f}")

    custom_test_file = f"{dataset_path}/10_rows.csv"
    custom_test_data = pd.read_csv(custom_test_file)

    X_custom, y_custom = preprocess_test_data(custom_test_file, events)

    # Step 15: Make predictions on the custom test table
    custom_test_predictions = best_model.predict(X_custom)

    # Step 16: Add predictions to the custom test table
    custom_test_data['Predict_Quantity'] = custom_test_predictions
    custom_test_data = custom_test_data.drop('Purchase_Quantity', axis=1)
    # Step 17: Save the updated table with predictions
    custom_test_data.to_csv('edamonia_backend/logic/train/prediction_results/LightGBM_predict.csv', index=False, encoding='utf-8-sig')

    raw_test['Predicted_Purchase_Quantity'] = y_test_pred

    # Збереження нової таблиці до CSV
    raw_test.to_csv('edamonia_backend/logic/train/prediction_results/LightGBM_test_predictions.csv', index=False, encoding='utf-8-sig')


    return {
        "model_name": "LightGBM",
        "parameters": {
            "n_estimators": best_params['n_estimators'],
            "num_leaves": best_params["num_leaves"],
            "learning_rate": best_params["learning_rate"],
            "max_depth": best_params["max_depth"]
        },
        "cv_metrics": {
            "mse": best_score
        },
        "test_metrics": {
            "mse": test_mse,
            "rmse": test_rmse,
            "mae": test_mae,
            "r2": test_r2
        }
    }